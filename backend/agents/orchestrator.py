"""
Orchestrator: full pipeline from screening through memo generation and storage.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from agents.memo_writer import MemoWriter
from agents.screener_agent import ScreenerAgent
from models.models import Memo

logger = logging.getLogger(__name__)


def _extract_recommendation(markdown_text: str) -> tuple[str, str]:
    """
    Parse recommendation and conviction from the generated memo text.
    Returns (recommendation, conviction) — both default to 'Watch'/'Medium' if not found.
    """
    recommendation = "Watch"
    conviction = "Medium"

    # Look for bold recommendation markers like **BUY**, **WATCH**, **PASS**
    rec_match = re.search(
        r"\*\*(BUY|WATCH|PASS)\*\*",
        markdown_text,
        re.IGNORECASE,
    )
    if rec_match:
        recommendation = rec_match.group(1).capitalize()

    # Look for conviction level
    conv_match = re.search(
        r"Conviction[:\s]+\*\*(High|Medium|Low)\*\*",
        markdown_text,
        re.IGNORECASE,
    )
    if conv_match:
        conviction = conv_match.group(1).capitalize()

    # Normalize
    if recommendation.upper() == "BUY":
        recommendation = "Buy"
    elif recommendation.upper() == "PASS":
        recommendation = "Pass"
    else:
        recommendation = "Watch"

    return recommendation, conviction


class Orchestrator:
    """
    Coordinates the full AlphaLens pipeline:
    1. Screen tickers by strategy + sector
    2. Fetch comprehensive data for top pick(s)
    3. Generate IC memo via Claude
    4. Persist to database
    """

    def __init__(self):
        self.screener = ScreenerAgent()
        self.memo_writer = MemoWriter()

    async def run(
        self,
        user_id: str,
        strategy: str,
        sector: str,
        num_picks: int = 1,
        db: Optional[AsyncSession] = None,
    ) -> Memo:
        """
        Full pipeline (non-streaming).

        Screens, generates, saves and returns the top Memo object.
        """
        # Step 1: Screen for top picks
        logger.info(f"Screening {sector}/{strategy} for user {user_id}")
        picks = await asyncio.to_thread(
            self.screener.screen, strategy, sector, num_picks
        )

        if not picks:
            raise ValueError(
                f"No qualifying tickers found for strategy='{strategy}', sector='{sector}'"
            )

        # Take the top pick
        top_pick = picks[0]
        ticker = top_pick["ticker"]
        company_name = top_pick["company_name"]
        data_package = top_pick["data_package"]

        logger.info(f"Top pick: {ticker} (score={top_pick['score']:.1f})")

        # Step 2: Generate memo
        markdown_text = await self.memo_writer.generate(
            ticker=ticker,
            strategy=strategy,
            sector=sector,
            data_package=data_package,
        )

        # Step 3: Parse recommendation
        recommendation, conviction = _extract_recommendation(markdown_text)

        # Step 4: Save to DB
        if db is not None:
            memo = await self._save_memo(
                db=db,
                user_id=user_id,
                ticker=ticker,
                company_name=company_name,
                strategy=strategy,
                sector=sector,
                recommendation=recommendation,
                conviction=conviction,
                markdown_text=markdown_text,
                data_package=data_package,
            )
            return memo
        else:
            # Return a transient Memo object (for testing without DB)
            memo = Memo(
                user_id=user_id,
                ticker=ticker,
                company_name=company_name,
                strategy=strategy,
                sector=sector,
                recommendation=recommendation,
                conviction=conviction,
                markdown_text=markdown_text,
                sources=["yfinance", "news_sentiment"],
                data_as_of=datetime.utcnow(),
            )
            return memo

    async def run_streaming(
        self,
        user_id: str,
        strategy: str,
        sector: str,
        num_picks: int = 1,
        db: Optional[AsyncSession] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming pipeline.

        Yields SSE-formatted chunks:
        - data: {"type": "status", "message": "..."} — progress updates
        - data: {"type": "token", "content": "..."} — memo text chunks
        - data: {"type": "done", "memo_id": "..."} — completion with memo ID
        """
        memo_id: Optional[str] = None

        try:
            # Step 1: Screen
            yield _sse("status", {"message": f"Screening {sector} sector for best {strategy} picks..."})

            picks = await asyncio.to_thread(
                self.screener.screen, strategy, sector, num_picks
            )

            if not picks:
                yield _sse("error", {"message": f"No qualifying tickers found for {strategy}/{sector}"})
                return

            top_pick = picks[0]
            ticker = top_pick["ticker"]
            company_name = top_pick["company_name"]
            data_package = top_pick["data_package"]

            yield _sse("status", {
                "message": f"Selected {ticker} ({company_name}) — strategy score {top_pick['score']:.0f}/100",
                "ticker": ticker,
                "company_name": company_name,
                "score": top_pick["score"],
            })

            # Step 2: Stream memo generation
            yield _sse("status", {"message": "Generating IC memo..."})

            full_text_chunks = []

            async for chunk in self.memo_writer.generate_streaming(
                ticker=ticker,
                strategy=strategy,
                sector=sector,
                data_package=data_package,
            ):
                full_text_chunks.append(chunk)
                yield _sse("token", {"content": chunk})

            markdown_text = "".join(full_text_chunks)

            # Step 3: Parse recommendation
            recommendation, conviction = _extract_recommendation(markdown_text)

            # Step 4: Save to DB
            if db is not None:
                memo = await self._save_memo(
                    db=db,
                    user_id=user_id,
                    ticker=ticker,
                    company_name=company_name,
                    strategy=strategy,
                    sector=sector,
                    recommendation=recommendation,
                    conviction=conviction,
                    markdown_text=markdown_text,
                    data_package=data_package,
                )
                memo_id = memo.id

            yield _sse("done", {
                "memo_id": memo_id,
                "ticker": ticker,
                "recommendation": recommendation,
                "conviction": conviction,
            })

        except Exception as e:
            logger.error(f"Orchestrator error: {e}", exc_info=True)
            yield _sse("error", {"message": str(e)})

    async def _save_memo(
        self,
        db: AsyncSession,
        user_id: str,
        ticker: str,
        company_name: str,
        strategy: str,
        sector: str,
        recommendation: str,
        conviction: str,
        markdown_text: str,
        data_package: dict,
    ) -> Memo:
        """Persist a memo to the database and return the ORM object."""
        memo = Memo(
            user_id=user_id,
            ticker=ticker,
            company_name=company_name,
            strategy=strategy,
            sector=sector,
            recommendation=recommendation,
            conviction=conviction,
            markdown_text=markdown_text,
            sources=["yfinance", "news_sentiment"],
            eval_scores=None,
            thinking_trace=None,
            data_as_of=datetime.utcnow(),
        )

        db.add(memo)
        await db.commit()
        await db.refresh(memo)

        logger.info(f"Saved memo {memo.id} for {ticker}")
        return memo


def _sse(event_type: str, data: dict) -> str:
    """Format a dict as an SSE data line."""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"
