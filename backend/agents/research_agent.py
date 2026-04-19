"""
Research Agent — uses Claude with tool use to deeply research a stock.

Claude decides what to look up, calls tools iteratively in a multi-turn loop,
and produces a ResearchPack containing all gathered data plus an analyst synthesis.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from tools.financial_tools import FINANCIAL_TOOLS, execute_tool

logger = logging.getLogger(__name__)


@dataclass
class ResearchPack:
    """Container for all research data gathered about a stock."""

    ticker: str
    strategy: str
    sector: str
    fundamentals: dict = field(default_factory=dict)
    price_data: dict = field(default_factory=dict)
    sec_excerpts: list[dict] = field(default_factory=list)  # RAG results with source metadata
    news_sentiment: dict = field(default_factory=dict)
    sector_context: dict = field(default_factory=dict)
    analyst_notes: str = ""  # Claude's final synthesis text
    tool_calls_made: list[str] = field(default_factory=list)

    def to_context_string(self) -> str:
        """Serialize to a JSON string suitable for passing to other agents."""
        return json.dumps(
            {
                "ticker": self.ticker,
                "strategy": self.strategy,
                "sector": self.sector,
                "fundamentals": self.fundamentals,
                "price_data": self.price_data,
                "sec_excerpts": self.sec_excerpts,
                "news_sentiment": self.news_sentiment,
                "sector_context": self.sector_context,
                "analyst_notes": self.analyst_notes,
            },
            indent=2,
            default=str,
        )


class ResearchAgent:
    """
    Runs a multi-turn tool-use loop with Claude to research a stock.

    Claude is given the FINANCIAL_TOOLS schema and decides which tools to call.
    After gathering data, Claude writes a structured synthesis as its final response.
    """

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-sonnet-4-6"
        self.max_turns = 8
        self._load_system_prompt()

    def _load_system_prompt(self) -> None:
        prompt_path = (
            Path(__file__).parent.parent / "prompts" / "system" / "research_agent.txt"
        )
        try:
            self.system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error(f"Research agent system prompt not found at {prompt_path}")
            raise

    async def research(
        self,
        ticker: str,
        strategy: str,
        sector: str,
        initial_data: dict,
    ) -> ResearchPack:
        """
        Run multi-turn tool use loop to research a ticker.

        initial_data is the basic data package from the screener
        (contains fundamentals + price_history + news_sentiment already).
        Returns a fully populated ResearchPack.
        """
        pack = ResearchPack(ticker=ticker, strategy=strategy, sector=sector)

        # Seed with screener's initial data
        pack.fundamentals = {
            k: v
            for k, v in initial_data.items()
            if k not in ("price_history", "news_sentiment", "strategy", "sector", "score")
        }
        pack.price_data = initial_data.get("price_history", {})
        pack.news_sentiment = initial_data.get("news_sentiment", {})

        # Truncate initial data for the user message to keep prompt size manageable
        initial_summary = json.dumps(initial_data, indent=2, default=str)
        if len(initial_summary) > 3000:
            initial_summary = initial_summary[:3000] + "\n... [truncated]"

        user_msg = (
            f"Research {ticker} for a {strategy} investment analysis in the {sector} sector.\n\n"
            f"I have some initial data from the screener:\n{initial_summary}\n\n"
            "Please use the available tools to:\n"
            "1. Dig deeper into the financials and full price history\n"
            "2. Search SEC filings for business model, competitive advantages, and risk factors\n"
            "3. Get recent news sentiment\n"
            "4. Get sector context and peer comparison\n\n"
            "After completing your research, write a structured synthesis as described in your instructions."
        )

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_msg}]
        tool_calls_made: list[str] = []

        for turn in range(self.max_turns):
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=self.system_prompt,
                    tools=FINANCIAL_TOOLS,
                    messages=messages,
                )
            except Exception as e:
                logger.error(f"ResearchAgent API call failed on turn {turn}: {e}")
                break

            # Append assistant response to conversation
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Extract the final text as analyst notes
                for block in response.content:
                    if hasattr(block, "text"):
                        pack.analyst_notes = block.text
                logger.info(
                    f"ResearchAgent finished for {ticker} in {turn + 1} turns. "
                    f"Tools called: {tool_calls_made}"
                )
                break

            if response.stop_reason == "tool_use":
                tool_results: list[dict] = []

                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_calls_made.append(tool_name)

                        logger.info(
                            f"ResearchAgent calling tool: {tool_name} "
                            f"with input: {json.dumps(tool_input, default=str)[:200]}"
                        )

                        try:
                            result_str = await execute_tool(tool_name, tool_input)
                        except Exception as e:
                            result_str = json.dumps({"error": str(e), "tool": tool_name})

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_str,
                            }
                        )

                        # Populate ResearchPack from tool results
                        try:
                            result_data = json.loads(result_str)
                            if "error" not in result_data:
                                if tool_name == "get_fundamentals":
                                    pack.fundamentals.update(result_data)
                                elif tool_name == "get_price_history":
                                    pack.price_data.update(result_data)
                                elif tool_name == "search_sec_filings":
                                    excerpts = (
                                        result_data
                                        if isinstance(result_data, list)
                                        else []
                                    )
                                    pack.sec_excerpts.extend(excerpts)
                                elif tool_name == "get_news_sentiment":
                                    pack.news_sentiment = result_data
                                elif tool_name == "get_sector_context":
                                    pack.sector_context = result_data
                        except json.JSONDecodeError:
                            pass

                messages.append({"role": "user", "content": tool_results})

            else:
                # Unexpected stop reason — extract any text and break
                for block in response.content:
                    if hasattr(block, "text"):
                        pack.analyst_notes = block.text
                break

        pack.tool_calls_made = tool_calls_made
        return pack
