"""
Bull Agent — writes the affirmative investment case using extended thinking.

Never sees the Bear Agent's output (independent reasoning).
Runs in parallel with BearAgent via asyncio.gather in the Orchestrator.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from .research_agent import ResearchPack

logger = logging.getLogger(__name__)


@dataclass
class BullCase:
    """Container for the bull investment case."""

    ticker: str
    thesis: str  # 2-3 sentence core thesis
    key_strengths: list[str]  # financial data-backed strengths
    catalysts: list[str]  # near-term catalysts
    valuation_support: str  # why current price is attractive
    upside_target: str  # price target or % upside
    full_text: str  # complete bull case markdown
    thinking_trace: list[dict] = field(default_factory=list)  # extended thinking blocks


def _extract_section(text: str, section_hint: str) -> str:
    """
    Extract a specific section from the bull/bear case text.

    Tries to find a header matching the section_hint and returns the content
    under it. Falls back to returning the first 500 characters of the full text.
    """
    # Try to match a markdown header containing the hint
    pattern = rf"(?:^|\n)#{1,3}[^#\n]*{re.escape(section_hint)}[^#\n]*\n(.*?)(?=\n#{1,3}|\Z)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()[:1000]

    # Fallback: return beginning of full text
    return text[:500].strip()


def _extract_list(text: str, section_hint: str) -> list[str]:
    """
    Extract bullet points from a section of text.

    Returns a list of strings (stripped of bullet markers).
    Falls back to empty list if section not found.
    """
    section_text = _extract_section(text, section_hint)
    if not section_text:
        return []

    # Match lines starting with - or * or numbered list
    lines = section_text.split("\n")
    bullets = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^[-*•]\s+", stripped):
            bullets.append(re.sub(r"^[-*•]\s+", "", stripped))
        elif re.match(r"^\d+\.\s+", stripped):
            bullets.append(re.sub(r"^\d+\.\s+", "", stripped))

    return bullets[:6]  # cap at 6 items


class BullAgent:
    """
    Generates the affirmative investment case for a stock using Claude
    with extended thinking enabled.
    """

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-sonnet-4-6"
        self._load_system_prompt()

    def _load_system_prompt(self) -> None:
        prompt_path = (
            Path(__file__).parent.parent / "prompts" / "system" / "bull_agent.txt"
        )
        try:
            self.system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error(f"Bull agent system prompt not found at {prompt_path}")
            raise

    async def write_bull_case(self, research_pack: ResearchPack) -> BullCase:
        """
        Generate the bull case, optionally with extended thinking.

        Thinking is controlled by the THINKING_BUDGET env var (default 1024).
        Set THINKING_BUDGET=0 to disable thinking entirely (dev/low-cost mode).
        Minimum effective budget when enabled is 1024 tokens (API requirement).
        """
        context = research_pack.to_context_string()
        # Cap context size to avoid excessive token usage
        if len(context) > 8000:
            context = context[:8000] + "\n... [truncated for length]"

        user_msg = (
            f"Write the bull case for {research_pack.ticker} "
            f"({research_pack.strategy} strategy, {research_pack.sector} sector).\n\n"
            f"Research data:\n{context}\n\n"
            "Write a compelling, data-backed bull case. "
            "Be specific — cite actual numbers from the data. "
            "Follow the structure defined in your system instructions."
        )

        thinking_budget = int(os.getenv("THINKING_BUDGET", "1024"))
        api_kwargs: dict = dict(
            model=self.model,
            max_tokens=3000,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        if thinking_budget >= 1024:
            api_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

        try:
            response = await self.client.messages.create(**api_kwargs)
        except Exception as e:
            logger.error(f"BullAgent API call failed for {research_pack.ticker}: {e}")
            raise

        thinking_blocks: list[dict] = []
        text_content = ""

        for block in response.content:
            if block.type == "thinking":
                thinking_blocks.append({"type": "thinking", "thinking": block.thinking})
            elif block.type == "text":
                text_content += block.text

        logger.info(
            f"BullAgent completed for {research_pack.ticker}. "
            f"Thinking blocks: {len(thinking_blocks)}, "
            f"Output length: {len(text_content)} chars"
        )

        return BullCase(
            ticker=research_pack.ticker,
            thesis=_extract_section(text_content, "thesis"),
            key_strengths=_extract_list(text_content, "strength"),
            catalysts=_extract_list(text_content, "catalyst"),
            valuation_support=_extract_section(text_content, "valuation"),
            upside_target=_extract_section(text_content, "target"),
            full_text=text_content,
            thinking_trace=thinking_blocks,
        )
