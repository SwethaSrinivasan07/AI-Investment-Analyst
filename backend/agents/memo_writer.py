"""
MemoWriter: generates IC investment memos using the Claude API.

Uses claude-sonnet-4-6 with streaming and prompt caching on the system prompt.
"""

import json
import logging
import os
from pathlib import Path
from typing import AsyncGenerator

import anthropic

from models.database import settings

logger = logging.getLogger(__name__)

# Path to the system prompt template
SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system" / "memo_writer.txt"

# Claude model per CLAUDE.md
MODEL = "claude-sonnet-4-6"

# Max tokens for memo generation
MAX_TOKENS = 4096


def _load_system_prompt() -> str:
    """Load the memo writer system prompt from disk."""
    try:
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error(f"System prompt not found at {SYSTEM_PROMPT_PATH}")
        raise


def _build_user_message(
    ticker: str,
    strategy: str,
    sector: str,
    data_package: dict,
    research_pack=None,
    bull_case=None,
    bear_case=None,
) -> str:
    """
    Build the user message that contains all financial context.
    We pass data as structured context so Claude never has to hallucinate numbers.

    When research_pack, bull_case, and bear_case are provided (Week 2 pipeline),
    the message is enriched with SEC excerpts, analyst notes, and the bull/bear arguments.
    """
    data_json = json.dumps(data_package, indent=2, default=str)
    # Cap raw data to avoid overly long prompts
    if len(data_json) > 4000:
        data_json = data_json[:4000] + "\n... [truncated]"

    base = (
        f"Please write a comprehensive IC investment memo for the following equity position.\n\n"
        f"## Requested Strategy: {strategy.upper()}\n"
        f"## Sector: {sector}\n"
        f"## Ticker: {ticker}\n\n"
        f"## Financial Data Package\n"
        f"The following data was fetched as of the as_of_date field. Use ONLY these numbers.\n\n"
        f"```json\n{data_json}\n```\n"
    )

    # Append research-pack enrichments if available (Week 2)
    if research_pack is not None:
        analyst_notes = getattr(research_pack, "analyst_notes", "")
        if analyst_notes:
            base += f"\n## Research Analyst Notes\n{analyst_notes[:2000]}\n"

        sec_excerpts = getattr(research_pack, "sec_excerpts", [])
        if sec_excerpts:
            base += (
                "\n## Key SEC Filing Excerpts (RAG-retrieved from real filings)\n"
                "_When you cite facts from these excerpts, use the format: "
                "[Source: TICKER FORM DATE] — e.g. [Source: NVDA 10-K 2024-01-26]_\n"
            )
            for i, excerpt in enumerate(sec_excerpts[:8]):
                text = excerpt.get("text", "")[:600]
                doc_type = excerpt.get("doc_type", "")
                filing_date = excerpt.get("filing_date", "")
                base += f"\n**Excerpt {i+1}** ({doc_type}, {filing_date}):\n> {text}\n"

    if bull_case is not None:
        bull_text = getattr(bull_case, "full_text", "")
        if bull_text:
            bull_trimmed = bull_text[:2000]
            base += f"\n## Bull Case (Independent Analysis)\n{bull_trimmed}\n"

    if bear_case is not None:
        bear_text = getattr(bear_case, "full_text", "")
        if bear_text:
            bear_trimmed = bear_text[:2000]
            base += f"\n## Bear Case (Independent Analysis)\n{bear_trimmed}\n"

    base += (
        "\nWrite the full IC memo following the structure in your system instructions. "
        "Synthesize the bull and bear cases into a balanced, well-reasoned recommendation. "
        "Ensure the recommendation and conviction level are clearly stated in the Executive Summary."
    )

    return base


# Pricing for claude-sonnet-4-6 (per million tokens, USD)
_PRICE = {
    "input": 3.00,
    "output": 15.00,
    "cache_write": 3.75,
    "cache_read": 0.30,
}


def _estimate_cost(usage) -> dict:
    """Convert Anthropic usage object → cost dict."""
    input_tok = getattr(usage, "input_tokens", 0) or 0
    output_tok = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cost = (
        (input_tok / 1_000_000) * _PRICE["input"]
        + (output_tok / 1_000_000) * _PRICE["output"]
        + (cache_read / 1_000_000) * _PRICE["cache_read"]
        + (cache_write / 1_000_000) * _PRICE["cache_write"]
    )
    return {
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_write,
        "estimated_cost_usd": round(cost, 5),
    }


class MemoWriter:
    """
    Generates IC investment memos using the Claude API.
    Supports both streaming and non-streaming generation.
    """

    def __init__(self):
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
        )
        self._system_prompt = _load_system_prompt()
        self.last_usage: dict = {}  # populated after each generation call

    async def generate_streaming(
        self,
        ticker: str,
        strategy: str,
        sector: str,
        data_package: dict,
        research_pack=None,
        bull_case=None,
        bear_case=None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream the memo as text chunks.

        Yields raw text delta strings as they arrive from Claude.
        Uses prompt caching on the system prompt for cost efficiency.

        When research_pack, bull_case, and bear_case are provided, the prompt
        is enriched with SEC excerpts, analyst notes, and the bull/bear arguments.
        """
        user_message = _build_user_message(
            ticker, strategy, sector, data_package,
            research_pack=research_pack,
            bull_case=bull_case,
            bear_case=bear_case,
        )

        # System prompt with cache_control so it's cached across requests
        system = [
            {
                "type": "text",
                "text": self._system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        async with self._client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[
                {"role": "user", "content": user_message}
            ],
        ) as stream:
            async for text_chunk in stream.text_stream:
                yield text_chunk
            try:
                final_message = await stream.get_final_message()
                self.last_usage = _estimate_cost(final_message.usage)
                logger.info(
                    f"Memo streamed for {ticker}. "
                    f"Input: {self.last_usage['input_tokens']} tok, "
                    f"Cache read: {self.last_usage['cache_read_tokens']} tok, "
                    f"Output: {self.last_usage['output_tokens']} tok, "
                    f"Est. cost: ${self.last_usage['estimated_cost_usd']:.4f}"
                )
            except Exception:
                pass

    async def generate(
        self,
        ticker: str,
        strategy: str,
        sector: str,
        data_package: dict,
        research_pack=None,
        bull_case=None,
        bear_case=None,
    ) -> str:
        """
        Generate a complete memo and return the full markdown text.

        Uses prompt caching on the system prompt.
        When research_pack, bull_case, and bear_case are provided, the prompt
        is enriched with SEC excerpts, analyst notes, and the bull/bear arguments.
        """
        user_message = _build_user_message(
            ticker, strategy, sector, data_package,
            research_pack=research_pack,
            bull_case=bull_case,
            bear_case=bear_case,
        )

        system = [
            {
                "type": "text",
                "text": self._system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        chunks = []
        async with self._client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[
                {"role": "user", "content": user_message}
            ],
        ) as stream:
            async for text_chunk in stream.text_stream:
                chunks.append(text_chunk)

            final_message = await stream.get_final_message()
            self.last_usage = _estimate_cost(final_message.usage)
            logger.info(
                f"Memo generated for {ticker}. "
                f"Input: {self.last_usage['input_tokens']} tok, "
                f"Cache read: {self.last_usage['cache_read_tokens']} tok, "
                f"Output: {self.last_usage['output_tokens']} tok, "
                f"Est. cost: ${self.last_usage['estimated_cost_usd']:.4f}"
            )

        return "".join(chunks)

    async def generate_with_chat_context(
        self,
        system_prompt_path: Path,
        memo_markdown: str,
        data_package: dict,
        chat_history: list[dict],
        new_user_message: str,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming chat response with memo context.

        This is used by the chat endpoint to provide follow-up Q&A on a memo.
        - system_prompt_path: path to the chat_analyst system prompt
        - memo_markdown: the full memo text for context
        - data_package: raw financial data
        - chat_history: list of {"role": "user"|"assistant", "content": str}
        - new_user_message: the new question from the user
        """
        chat_system_prompt = Path(system_prompt_path).read_text(encoding="utf-8")

        # Build context injection as the first user message
        context_message = f"""Here is the investment memo I wrote, plus the underlying financial data:

## Investment Memo
{memo_markdown}

## Underlying Financial Data
```json
{json.dumps(data_package, indent=2, default=str)}
```

I'm ready to answer your questions about this analysis."""

        # Build the full messages array
        # First message is the context injection (assistant acknowledges it)
        messages = [
            {"role": "user", "content": context_message},
            {
                "role": "assistant",
                "content": "I have the memo and financial data in front of me. What would you like to know?",
            },
        ]

        # Add existing chat history
        for msg in chat_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Add the new user question
        messages.append({"role": "user", "content": new_user_message})

        # Cache the system prompt
        system = [
            {
                "type": "text",
                "text": chat_system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        async with self._client.messages.stream(
            model=MODEL,
            max_tokens=2048,
            system=system,
            messages=messages,
        ) as stream:
            async for text_chunk in stream.text_stream:
                yield text_chunk
