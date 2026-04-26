"""
Backtests API:
- POST /api/backtests/run  — trigger a new backtest (runs synchronously, returns result)
- GET  /api/backtests      — list available backtest results
- GET  /api/backtests/{id} — get a specific backtest result

Register in main.py:
    app.include_router(backtests_router, prefix="/api/backtests", tags=["backtests"])
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from models.database import get_db
from models.models import BacktestResult, User
from services.backtester import run_backtest

router = APIRouter()
logger = logging.getLogger(__name__)

# How long to consider a cached backtest result still fresh (7 days)
CACHE_TTL_DAYS = 7


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class BacktestRunRequest(BaseModel):
    strategy: str   # momentum | value | growth | dividend
    sector: str
    period: str = "1y"  # "1y" | "2y"


class BacktestMetricsSchema(BaseModel):
    cumulative_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    alpha_vs_spy_pct: float
    volatility_pct: float


class BacktestResultResponse(BaseModel):
    id: str
    strategy: str
    sector: str
    period: str
    metrics: dict
    chart_data: list
    created_at: datetime

    class Config:
        from_attributes = True


class BacktestSummaryResponse(BaseModel):
    id: str
    strategy: str
    sector: str
    period: str
    metrics: dict
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# POST /run — run or return cached backtest
# ---------------------------------------------------------------------------

@router.post("/run", response_model=BacktestResultResponse)
async def run_backtest_endpoint(
    req: BacktestRunRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a backtest for the given strategy + sector + period.

    If a result was already computed within the last 7 days for the same
    parameters, it is returned from the cache (DB) immediately without
    re-running the simulation.
    """
    strategy = req.strategy.lower().strip()
    sector = req.sector.strip()
    period = req.period.strip()

    valid_strategies = {"momentum", "value", "growth", "dividend"}
    if strategy not in valid_strategies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid strategy '{strategy}'. Must be one of: {sorted(valid_strategies)}",
        )

    valid_periods = {"1y", "2y"}
    if period not in valid_periods:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid period '{period}'. Must be '1y' or '2y'.",
        )

    # ------------------------------------------------------------------
    # Check for a recent cached result
    # ------------------------------------------------------------------
    cutoff = datetime.utcnow() - timedelta(days=CACHE_TTL_DAYS)
    stmt = (
        select(BacktestResult)
        .where(
            BacktestResult.strategy == strategy,
            BacktestResult.sector == sector,
            BacktestResult.period == period,
            BacktestResult.created_at >= cutoff,
        )
        .order_by(desc(BacktestResult.created_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        logger.info(
            "Returning cached backtest %s for %s/%s/%s (created %s)",
            existing.id, strategy, sector, period, existing.created_at,
        )
        return existing

    # ------------------------------------------------------------------
    # Run the backtest in a thread (synchronous, CPU/IO bound)
    # ------------------------------------------------------------------
    logger.info("Running new backtest: strategy=%s sector=%s period=%s", strategy, sector, period)

    try:
        backtest_output = await asyncio.to_thread(run_backtest, strategy, sector, period)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error running backtest")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {exc}",
        )

    # ------------------------------------------------------------------
    # Persist result
    # ------------------------------------------------------------------
    db_record = BacktestResult(
        strategy=strategy,
        sector=sector,
        period=period,
        metrics=backtest_output["metrics"],
        chart_data=backtest_output["chart_data"],
    )
    db.add(db_record)
    await db.commit()
    await db.refresh(db_record)

    logger.info("Saved backtest result %s", db_record.id)
    return db_record


# ---------------------------------------------------------------------------
# GET / — list all backtest results (summary, no chart_data)
# ---------------------------------------------------------------------------

@router.get("", response_model=list[BacktestSummaryResponse])
async def list_backtests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all stored backtest summaries, newest first."""
    stmt = select(BacktestResult).order_by(desc(BacktestResult.created_at))
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return rows


# ---------------------------------------------------------------------------
# GET /{id} — full result including chart_data
# ---------------------------------------------------------------------------

@router.get("/{backtest_id}", response_model=BacktestResultResponse)
async def get_backtest(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a specific backtest result including full chart data."""
    stmt = select(BacktestResult).where(BacktestResult.id == backtest_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest not found")
    return record

# Register in main.py: app.include_router(router, prefix="/api/backtests", tags=["backtests"])
