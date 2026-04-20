"""
Bear Agent — writes the adversarial bear case using extended thinking.

NEVER sees the Bull Agent's output. Runs in parallel via asyncio.gather.
Independent reasoning — no shared context with BullAgent.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from .research_agent import ResearchPack
from .bull_agent import _extract_section, _extract_list  # reuse helpers
from models.database import settings

logger = logging.getLogger(__name__)


@dataclass
class BearCase:
    """Container for the adversarial bear investment case."""

    ticker: str
    risk_thesis: str  # 2-3 sentence core risk thesis
    key_risks: list[str]  # specific risks with data
    financial_weaknesses: list[str]  # balance sheet / income statement concerns
    downside_scenario: str  # specific downside target and scenario
    full_text: str  # complete bear case markdown
    thinking_trace: list[dict] = field(default_factory=list)  # extended thinking blocks


class BearAgent:
    """
    Generates the adversarial bear case for a stock using Claude
    with extended thinking enabled.

    Runs independently of BullAgent — receives the same ResearchPack
    but reasons without seeing the bull argument.
    """

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-sonnet-4-6"
        self._load_system_prompt()

    def _load_system_prompt(self) -> None:
        prompt_path = (
            Path(__file__).parent.parent / "prompts" / "system" / "bear_agent.txt"
        )
        try:
            self.system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error(f"Bear agent system prompt not found at {prompt_path}")
            raise

    async def write_bear_case(self, research_pack: ResearchPack) -> BearCase:
        """
        Generate the bear case with extended thinking.

        Uses claude-sonnet-4-6 with thinking budget to allow deeper critical
        reasoning before producing the final written bear argument.
        """
        context = research_pack.to_context_string()
        # Cap context size to avoid excessive token usage
        if len(context) > 8000:
            context = context[:8000] + "\n... [truncated for length]"

        user_msg = (
            f"Write the bear case for {research_pack.ticker} "
            f"({research_pack.strategy} strategy, {research_pack.sector} sector).\n\n"
            f"Research data:\n{context}\n\n"
            "Write a rigorous, specific bear case. "
            "Identify real risks with actual numbers. "
            "Do not hedge — commit to the bear thesis. "
            "Follow the structure defined in your system instructions."
        )

        thinking_budget = settings.thinking_budget
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
            logger.error(f"BearAgent API call failed for {research_pack.ticker}: {e}")
            raise

        thinking_blocks: list[dict] = []
        text_content = ""

        for block in response.content:
            if block.type == "thinking":
                thinking_blocks.append({"type": "thinking", "thinking": block.thinking})
            elif block.type == "text":
                text_content += block.text

        logger.info(
            f"BearAgent completed for {research_pack.ticker}. "
            f"Thinking blocks: {len(thinking_blocks)}, "
            f"Output length: {len(text_content)} chars"
        )

        return BearCase(
            ticker=research_pack.ticker,
            risk_thesis=_extract_section(text_content, "thesis"),
            key_risks=_extract_list(text_content, "risk"),
            financial_weaknesses=_extract_list(text_content, "weakness"),
            downside_scenario=_extract_section(text_content, "downside"),
            full_text=text_content,
            thinking_trace=thinking_blocks,
        )
