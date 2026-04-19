"""
Orchestrator v2 — Full multi-agent pipeline:
  ScreenerAgent → ResearchAgent → [BullAgent ‖ BearAgent] → MemoWriter → EvalAgent

The streaming variant yields SSE-formatted chunks so the frontend can display
real-time progress and token-by-token memo text.
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import update

from agents.bear_agent import BearAgent
from agents.bull_agent import BullAgent
from agents.eval_agent import EvalAgent
from agents.memo_writer import MemoWriter
from agents.research_agent import ResearchAgent
from agents.screener_agent import ScreenerAgent
from models.database import AsyncSessionLocal
from models.models import Memo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_recommendation(text: str) -> str:
    """Extract BUY / WATCH / PASS from memo text."""
    text_upper = text.upper()
    # Bold markers take priority
    if "**BUY**" in text_upper or "RECOMMENDATION: BUY" in text_upper:
        return "Buy"
    if "**PASS**" in text_upper or "RECOMMENDATION: PASS" in text_upper:
        return "Pass"
    # Looser match
    if re.search(r"\bBUY\b", text_upper):
        return "Buy"
    if re.search(r"\bPASS\b", text_upper):
        return "Pass"
    return "Watch"


def _parse_conviction(text: str) -> str:
    """Extract High / Medium / Low conviction from memo text."""
    text_upper = text.upper()
    if "HIGH CONVICTION" in text_upper or "CONVICTION: HIGH" in text_upper or "CONVICTION**:? HIGH" in text_upper:
        return "High"
    if "LOW CONVICTION" in text_upper or "CONVICTION: LOW" in text_upper:
        return "Low"
    # Bold markers
    if "**HIGH**" in text_upper and "CONVICTION" in text_upper:
        return "High"
    if "**LOW**" in text_upper and "CONVICTION" in text_upper:
        return "Low"
    return "Medium"


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


async def _run_eval_background(
    eval_agent: EvalAgent, memo_id: str, memo_text: str
) -> None:
    """
    Run evaluation and persist scores to the DB.

    Designed to run as a fire-and-forget asyncio.create_task.
    Any failure is silently swallowed — eval never affects the user.
    """
    try:
        result = await eval_agent.evaluate(memo_id, memo_text)
        async with AsyncSessionLocal() as db2:
            await db2.execute(
                update(Memo)
                .where(Memo.id == memo_id)
                .values(
                    eval_scores={
                        "data_grounding": result.data_grounding,
                        "thesis_clarity": result.thesis_clarity,
                        "risk_depth": result.risk_depth,
                        "valuation_rigor": result.valuation_rigor,
                        "actionability": result.actionability,
                        "overall": result.overall,
                        "rationale": result.rationale,
                    }
                )
            )
            await db2.commit()
        logger.info(f"Eval scores saved for memo {memo_id}: overall={result.overall}")
    except Exception as e:
        logger.error(f"Background eval failed for memo {memo_id}: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """
    Coordinates the full AlphaLens Week 2 pipeline:

    1. Screen → pick top ticker for strategy + sector
    2. Research → multi-turn tool use loop (fundamentals, price, SEC filings, news, peers)
    3. Bull + Bear → parallel extended-thinking agents (independent, no shared context)
    4. MemoWriter → synthesis into IC-format markdown memo
    5. Persist → save Memo to SQLite
    6. Eval → async background scoring (non-blocking)
    """

    def __init__(self):
        self.screener = ScreenerAgent()
        self.researcher = ResearchAgent()
        self.bull = BullAgent()
        self.bear = BearAgent()
        self.writer = MemoWriter()
        self.eval = EvalAgent()

    # ------------------------------------------------------------------
    # Non-streaming pipeline
    # ------------------------------------------------------------------

    async def run(
        self,
        user_id: str,
        strategy: str,
        sector: str,
        num_picks: int = 1,
        db=None,  # AsyncSession | None — kept for backward compatibility
    ) -> Memo:
        """
        Full non-streaming pipeline. Returns the saved Memo ORM object.

        The db parameter is accepted for backward compatibility but the
        orchestrator now manages its own DB sessions internally.
        """
        # 1. Screen
        logger.info(f"[Orchestrator] Screening {sector}/{strategy} for user {user_id}")
        candidates = await asyncio.to_thread(
            self.screener.screen, strategy, sector, num_picks
        )
        if not candidates:
            raise ValueError(
                f"No qualifying tickers found for strategy='{strategy}', sector='{sector}'"
            )

        top = candidates[0]
        ticker: str = top["ticker"]
        company_name: str = top.get("company_name", ticker)
        data_package: dict = top.get("data_package", {})

        logger.info(f"[Orchestrator] Top pick: {ticker} (score={top['score']:.1f})")

        # 2. Research (multi-turn tool use)
        logger.info(f"[Orchestrator] Researching {ticker}...")
        research_pack = await self.researcher.research(
            ticker=ticker,
            strategy=strategy,
            sector=sector,
            initial_data=data_package,
        )
        logger.info(
            f"[Orchestrator] Research complete. "
            f"Tools called: {research_pack.tool_calls_made}, "
            f"SEC excerpts: {len(research_pack.sec_excerpts)}"
        )

        # 3. Bull + Bear in parallel (independent — they don't share context)
        logger.info(f"[Orchestrator] Running Bull + Bear agents in parallel for {ticker}...")
        bull_case, bear_case = await asyncio.gather(
            self.bull.write_bull_case(research_pack),
            self.bear.write_bear_case(research_pack),
        )

        # 4. Generate memo (synthesis of everything)
        logger.info(f"[Orchestrator] Writing IC memo for {ticker}...")
        memo_text = await self.writer.generate(
            ticker=ticker,
            strategy=strategy,
            sector=sector,
            data_package=data_package,
            research_pack=research_pack,
            bull_case=bull_case,
            bear_case=bear_case,
        )

        # 5. Combine thinking traces
        all_thinking = bull_case.thinking_trace + bear_case.thinking_trace

        # 6. Collect sources from RAG
        sources = [
            {
                "text": chunk.get("text", "")[:200],
                "doc_type": chunk.get("doc_type", ""),
                "filing_date": chunk.get("filing_date", ""),
                "chunk_id": chunk.get("chunk_id", ""),
            }
            for chunk in research_pack.sec_excerpts
        ]

        # 7. Parse recommendation and conviction
        recommendation = _parse_recommendation(memo_text)
        conviction = _parse_conviction(memo_text)

        # 8. Persist to DB
        async with AsyncSessionLocal() as session:
            memo = Memo(
                id=str(uuid.uuid4()),
                user_id=user_id,
                ticker=ticker,
                company_name=company_name,
                strategy=strategy,
                sector=sector,
                recommendation=recommendation,
                conviction=conviction,
                markdown_text=memo_text,
                thinking_trace=all_thinking,
                sources=sources,
                data_as_of=datetime.utcnow(),
            )
            session.add(memo)
            await session.commit()
            await session.refresh(memo)

        # 9. Eval in background (fire-and-forget)
        asyncio.create_task(
            _run_eval_background(self.eval, memo.id, memo_text)
        )

        logger.info(
            f"[Orchestrator] Memo {memo.id} saved for {ticker} "
            f"({recommendation}, {conviction})"
        )
        return memo

    # ------------------------------------------------------------------
    # Streaming pipeline
    # ------------------------------------------------------------------

    async def run_streaming(
        self,
        user_id: str,
        strategy: str,
        sector: str,
        num_picks: int = 1,
        db=None,  # kept for backward compatibility
    ) -> AsyncGenerator[str, None]:
        """
        Streaming pipeline — yields SSE-formatted events.

        Event types:
        - {"type": "status", "message": "..."}          — progress updates
        - {"type": "token",  "content": "..."}           — memo text chunks
        - {"type": "done",   "memo_id": "...", ...}      — completion
        - {"type": "error",  "message": "..."}           — failure
        """
        try:
            # 1. Screen
            yield _sse({"type": "status", "message": f"Screening {sector} sector for {strategy} picks..."})
            candidates = await asyncio.to_thread(
                self.screener.screen, strategy, sector, num_picks
            )
            if not candidates:
                yield _sse({
                    "type": "error",
                    "message": f"No qualifying tickers found for {strategy}/{sector}",
                })
                return

            top = candidates[0]
            ticker: str = top["ticker"]
            company_name: str = top.get("company_name", ticker)
            data_package: dict = top.get("data_package", {})

            yield _sse({
                "type": "status",
                "message": f"Selected {ticker} ({company_name}) — score {top['score']:.0f}/100",
                "ticker": ticker,
                "company_name": company_name,
                "score": top["score"],
            })

            # 2. Research
            yield _sse({"type": "status", "message": f"Researching {ticker} — fetching financials, SEC filings, news..."})
            research_pack = await self.researcher.research(
                ticker=ticker,
                strategy=strategy,
                sector=sector,
                initial_data=data_package,
            )
            yield _sse({
                "type": "status",
                "message": (
                    f"Research complete. "
                    f"Tools used: {', '.join(set(research_pack.tool_calls_made))}. "
                    f"SEC excerpts: {len(research_pack.sec_excerpts)}. "
                    "Building bull and bear cases..."
                ),
            })

            # 3. Bull + Bear in parallel
            bull_case, bear_case = await asyncio.gather(
                self.bull.write_bull_case(research_pack),
                self.bear.write_bear_case(research_pack),
            )
            yield _sse({"type": "status", "message": "Bull and bear cases complete. Writing investment memo..."})

            # 4. Stream memo
            memo_text = ""
            async for chunk in self.writer.generate_streaming(
                ticker=ticker,
                strategy=strategy,
                sector=sector,
                data_package=data_package,
                research_pack=research_pack,
                bull_case=bull_case,
                bear_case=bear_case,
            ):
                memo_text += chunk
                yield _sse({"type": "token", "content": chunk})

            # 5. Persist
            all_thinking = bull_case.thinking_trace + bear_case.thinking_trace
            sources = [
                {
                    "text": c.get("text", "")[:200],
                    "doc_type": c.get("doc_type", ""),
                    "filing_date": c.get("filing_date", ""),
                    "chunk_id": c.get("chunk_id", ""),
                }
                for c in research_pack.sec_excerpts
            ]
            recommendation = _parse_recommendation(memo_text)
            conviction = _parse_conviction(memo_text)

            async with AsyncSessionLocal() as session:
                memo = Memo(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    ticker=ticker,
                    company_name=company_name,
                    strategy=strategy,
                    sector=sector,
                    recommendation=recommendation,
                    conviction=conviction,
                    markdown_text=memo_text,
                    thinking_trace=all_thinking,
                    sources=sources,
                    data_as_of=datetime.utcnow(),
                )
                session.add(memo)
                await session.commit()
                await session.refresh(memo)
                memo_id = memo.id

            # 6. Eval in background
            asyncio.create_task(
                _run_eval_background(self.eval, memo_id, memo_text)
            )

            yield _sse({
                "type": "done",
                "memo_id": memo_id,
                "ticker": ticker,
                "recommendation": recommendation,
                "conviction": conviction,
            })

        except Exception as e:
            logger.error(f"[Orchestrator streaming] Error: {e}", exc_info=True)
            yield _sse({"type": "error", "message": str(e)})
