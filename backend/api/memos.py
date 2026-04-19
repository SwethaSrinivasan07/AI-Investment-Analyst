"""
Memo API endpoints:
- POST /api/memos/generate       — non-streaming memo generation
- GET  /api/memos/generate/stream — SSE streaming memo generation
- GET  /api/memos                — list user's memos
- GET  /api/memos/{id}           — get single memo
- DELETE /api/memos/{id}         — delete memo
"""

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
    current_user: User = Depends(get_current_user_sse),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE streaming endpoint.
    Streams: status updates, token chunks, and a final done event.
    """
    strategy = _validate_strategy(strategy)

    async def event_generator():
        async for chunk in _orchestrator.run_streaming(
            user_id=current_user.id,
            strategy=strategy,
            sector=sector,
            num_picks=1,
            db=db,
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


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
