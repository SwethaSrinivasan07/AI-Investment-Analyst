"""
Stocks API endpoints:
- GET /api/stocks/{ticker}/price  — price history + technical indicators
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import get_current_user
from models.models import User
from services.data_fetcher import get_price_history

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{ticker}/price")
async def get_stock_price(
    ticker: str,
    current_user: User = Depends(get_current_user),
):
    """
    Return 3-month price history and key technical indicators for a ticker.

    Response shape:
      {
        "ticker": "AAPL",
        "current_price": 172.50,
        "price_change_1d_pct": 1.2,
        "price_change_1m_pct": 3.4,
        "price_change_3m_pct": 8.1,
        "price_change_1y_pct": 22.5,
        "rsi_14": 58.3,
        "data": [{"date": "2024-01-02", "close": 185.2}, ...]
      }

    Only date + close are included in the data array to keep the response small.
    """
    ticker = ticker.upper()

    try:
        raw = await asyncio.to_thread(get_price_history, ticker, "3mo")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.error(f"get_stock_price({ticker}): {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch price data for {ticker}.",
        )

    if not raw or not raw.get("data"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No price data found for ticker '{ticker}'.",
        )

    # Strip open/high/low/volume — only keep date + close
    slim_data = [
        {"date": row["date"], "close": row["close"]}
        for row in raw["data"]
    ]

    return {
        "ticker": raw["ticker"],
        "current_price": raw.get("current_price"),
        "price_change_1d_pct": raw.get("price_change_1d_pct"),
        "price_change_1m_pct": raw.get("price_change_1m_pct"),
        "price_change_3m_pct": raw.get("price_change_3m_pct"),
        "price_change_1y_pct": raw.get("price_change_1y_pct"),
        "rsi_14": raw.get("rsi_14"),
        "data": slim_data,
    }
