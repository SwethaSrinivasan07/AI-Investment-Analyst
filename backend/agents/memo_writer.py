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
) -> str:
    """
    Build the user message that contains all financial context.
    We pass data as structured context so Claude never has to hallucinate numbers.
    """
    data_json = json.dumps(data_package, indent=2, default=str)

    return f"""Please write a comprehensive IC investment memo for the following equity position.

## Requested Strategy: {strategy.upper()}
## Sector: {sector}
## Ticker: {ticker}

## Financial Data Package
The following data was fetched as of the as_of_date field. Use ONLY these numbers.

```json
{data_json}
```

Write the full IC memo following the structure in your system instructions. Ensure the recommendation and conviction level are clearly stated in the Executive Summary.
"""


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

    async def generate_streaming(
        self,
        ticker: str,
        strategy: str,
        sector: str,
        data_package: dict,
    ) -> AsyncGenerator[str, None]:
        """
        Stream the memo as text chunks.

        Yields raw text delta strings as they arrive from Claude.
        Uses prompt caching on the system prompt for cost efficiency.
        """
        user_message = _build_user_message(ticker, strategy, sector, data_package)

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

    async def generate(
        self,
        ticker: str,
        strategy: str,
        sector: str,
        data_package: dict,
    ) -> str:
        """
        Generate a complete memo and return the full markdown text.

        Uses prompt caching on the system prompt.
        """
        user_message = _build_user_message(ticker, strategy, sector, data_package)

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
            logger.info(
                f"Memo generated for {ticker}. "
                f"Input tokens: {final_message.usage.input_tokens}, "
                f"Cache read: {final_message.usage.cache_read_input_tokens}, "
                f"Output tokens: {final_message.usage.output_tokens}"
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
