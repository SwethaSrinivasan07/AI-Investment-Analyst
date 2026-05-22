"""
Memo API endpoints:
- POST /api/memos/generate       — non-streaming memo generation
- GET  /api/memos/generate/stream — SSE streaming memo generation
- GET  /api/memos                — list user's memos
- GET  /api/memos/{id}           — get single memo
- DELETE /api/memos/{id}         — delete memo
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.orchestrator import Orchestrator
from api.auth import get_current_user, get_current_user_sse
from models.database import get_db
from models.models import Memo, User

router = APIRouter()
logger = logging.getLogger(__name__)

# Shared orchestrator instance
_orchestrator = Orchestrator()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    strategy: str  # momentum | value | growth | dividend
    sector: str
    num_picks: int = 1
    ticker: Optional[str] = None  # if set, bypasses the screener


class MemoResponse(BaseModel):
    id: str
    ticker: str
    company_name: Optional[str]
    strategy: str
    sector: str
    recommendation: Optional[str]
    conviction: Optional[str]
    markdown_text: Optional[str]
    sources: Optional[list]
    eval_scores: Optional[dict]
    usage_stats: Optional[dict]
    data_as_of: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class MemoListItem(BaseModel):
    id: str
    ticker: str
    company_name: Optional[str]
    strategy: str
    sector: str
    recommendation: Optional[str]
    conviction: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_strategy(strategy: str) -> str:
    valid = {"momentum", "value", "growth", "dividend"}
    s = strategy.lower()
    if s not in valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"strategy must be one of: {sorted(valid)}",
        )
    return s


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=MemoResponse)
async def generate_memo(
    req: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger full pipeline (non-streaming): screen → generate → save → return.
    """
    strategy = _validate_strategy(req.strategy)

    try:
        memo = await _orchestrator.run(
            user_id=current_user.id,
            strategy=strategy,
            sector=req.sector,
            num_picks=max(1, min(req.num_picks, 5)),
            ticker=req.ticker,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"generate_memo error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Memo generation failed. Please try again.",
        )

    return MemoResponse.model_validate(memo)


@router.get("/generate/stream")
async def generate_memo_stream(
    strategy: str = Query(...),
    sector: str = Query(...),
    ticker: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user_sse),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE streaming endpoint.
    Streams: status updates, token chunks, and a final done event.
    Pass ticker= to bypass the screener and generate a memo for a specific stock.
    """
    strategy = _validate_strategy(strategy)

    async def event_generator():
        """
        Wraps run_streaming with a keepalive task that sends SSE pings every
        25 seconds. This prevents Render / nginx / browser from closing the
        connection during the long bull+bear agent phase (~60-120 s of silence).
        """
        queue: asyncio.Queue = asyncio.Queue()

        async def _pipeline() -> None:
            try:
                async for chunk in _orchestrator.run_streaming(
                    user_id=current_user.id,
                    strategy=strategy,
                    sector=sector,
                    num_picks=1,
                    ticker=ticker,
                    db=db,
                ):
                    await queue.put(chunk)
            finally:
                await queue.put(None)  # sentinel — signals the generator to stop

        async def _keepalive() -> None:
            ping = f"data: {json.dumps({'type': 'ping'})}\n\n"
            while True:
                await asyncio.sleep(25)
                await queue.put(ping)

        pipeline_task = asyncio.create_task(_pipeline())
        keepalive_task = asyncio.create_task(_keepalive())

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            keepalive_task.cancel()
            pipeline_task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/stats")
async def get_memo_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregate system metrics for the current user's memos.
    Used for the written report and system dashboard.
    """
    result = await db.execute(
        select(Memo).where(Memo.user_id == current_user.id)
    )
    memos = result.scalars().all()

    total_memos = len(memos)
    memos_with_sources = sum(1 for m in memos if m.sources and len(m.sources) > 0)
    grounding_rate = round(memos_with_sources / total_memos * 100, 1) if total_memos else 0

    # Eval score averages
    eval_dims = ["data_grounding", "thesis_clarity", "risk_depth", "valuation_rigor", "actionability", "overall"]
    eval_totals: dict[str, list[float]] = {d: [] for d in eval_dims}
    for m in memos:
        if m.eval_scores:
            for dim in eval_dims:
                val = m.eval_scores.get(dim)
                if val is not None:
                    eval_totals[dim].append(float(val))
    avg_eval = {
        dim: round(sum(vals) / len(vals), 2) if vals else None
        for dim, vals in eval_totals.items()
    }

    # Token usage aggregates
    total_input = total_output = total_cache_read = total_cache_creation = total_cost = 0.0
    memos_with_usage = 0
    for m in memos:
        if m.usage_stats:
            memos_with_usage += 1
            total_input += m.usage_stats.get("input_tokens", 0)
            total_output += m.usage_stats.get("output_tokens", 0)
            total_cache_read += m.usage_stats.get("cache_read_tokens", 0)
            total_cache_creation += m.usage_stats.get("cache_creation_tokens", 0)
            total_cost += m.usage_stats.get("estimated_cost_usd", 0)

    cache_savings_pct = None
    if total_cache_read + total_input > 0:
        full_cost = (total_cache_read + total_input) / 1_000_000 * 3.0  # if no caching
        actual_cache_cost = total_cache_read / 1_000_000 * 0.30
        saved = full_cost - actual_cache_cost
        cache_savings_pct = round(saved / full_cost * 100, 1) if full_cost > 0 else 0

    return {
        "total_memos": total_memos,
        "memos_with_sources": memos_with_sources,
        "grounding_rate_pct": grounding_rate,
        "avg_eval_scores": avg_eval,
        "token_usage": {
            "memos_tracked": memos_with_usage,
            "total_input_tokens": int(total_input),
            "total_output_tokens": int(total_output),
            "total_cache_read_tokens": int(total_cache_read),
            "total_cache_creation_tokens": int(total_cache_creation),
            "total_estimated_cost_usd": round(total_cost, 4),
            "avg_cost_per_memo_usd": round(total_cost / memos_with_usage, 4) if memos_with_usage else None,
            "cache_savings_pct": cache_savings_pct,
        },
        "eval_score_trend": [
            {
                "memo_id": m.id,
                "ticker": m.ticker,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "overall": m.eval_scores.get("overall") if m.eval_scores else None,
            }
            for m in sorted(memos, key=lambda x: x.created_at or datetime.min)
            if m.eval_scores
        ],
    }


@router.get("", response_model=list[MemoListItem])
async def list_memos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List the current user's memos, newest first."""
    result = await db.execute(
        select(Memo)
        .where(Memo.user_id == current_user.id)
        .order_by(desc(Memo.created_at))
        .limit(limit)
        .offset(offset)
    )
    memos = result.scalars().all()
    return [MemoListItem.model_validate(m) for m in memos]


@router.get("/{memo_id}", response_model=MemoResponse)
async def get_memo(
    memo_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single memo by ID. Only returns memos owned by the current user."""
    result = await db.execute(
        select(Memo).where(
            Memo.id == memo_id,
            Memo.user_id == current_user.id,
        )
    )
    memo = result.scalar_one_or_none()
    if memo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")
    return MemoResponse.model_validate(memo)


@router.delete("/{memo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memo(
    memo_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a memo. Only the owner can delete it."""
    result = await db.execute(
        select(Memo).where(
            Memo.id == memo_id,
            Memo.user_id == current_user.id,
        )
    )
    memo = result.scalar_one_or_none()
    if memo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo not found")

    await db.delete(memo)
    await db.commit()
