"""
Alpaca paper-trading integration for AlphaLens.

Always uses Alpaca's paper-trading environment — never live money unless the
user explicitly configures ALPACA_LIVE=true in .env (guarded below).

Required .env vars:
  ALPACA_API_KEY    — Alpaca paper key
  ALPACA_SECRET_KEY — Alpaca paper secret
  ALPACA_LIVE       — "true" to use live trading (default: false / paper)

Usage:
  from services.alpaca_service import place_order, get_order, get_positions
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_API_KEY    = os.getenv("ALPACA_API_KEY", "")
_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
_LIVE       = os.getenv("ALPACA_LIVE", "false").lower() == "true"
_BASE_URL   = "https://api.alpaca.markets" if _LIVE else "https://paper-api.alpaca.markets"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class OrderResult:
    alpaca_order_id: str
    ticker: str
    side: str          # buy | sell
    qty: float
    status: str        # accepted | pending_new | filled | rejected | cancelled
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    filled_avg_price: Optional[float] = None
    error: Optional[str] = None


@dataclass
class AlpacaPosition:
    ticker: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_plpc: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client():
    """Return a TradingClient, or raise if credentials are missing."""
    if not _API_KEY or not _SECRET_KEY:
        raise ValueError(
            "Alpaca credentials not configured. "
            "Add ALPACA_API_KEY and ALPACA_SECRET_KEY to backend/.env"
        )
    from alpaca.trading.client import TradingClient
    return TradingClient(_API_KEY, _SECRET_KEY, paper=not _LIVE)


def _is_configured() -> bool:
    return bool(_API_KEY and _SECRET_KEY)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def place_order(
    ticker: str,
    side: str,          # "buy" | "sell"
    qty: float,
    rationale: str = "",
) -> OrderResult:
    """
    Submit a market order to Alpaca (paper by default).
    Returns an OrderResult regardless of success/failure.
    """
    import asyncio

    def _submit():
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        client = _get_client()
        req = MarketOrderRequest(
            symbol=ticker.upper(),
            qty=qty,
            side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(req)
        return order

    try:
        order = await asyncio.to_thread(_submit)
        return OrderResult(
            alpaca_order_id=str(order.id),
            ticker=ticker.upper(),
            side=side.lower(),
            qty=float(qty),
            status=str(order.status.value) if hasattr(order.status, "value") else str(order.status),
            submitted_at=order.submitted_at,
            filled_at=order.filled_at,
            filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
        )
    except Exception as exc:
        logger.error("Alpaca place_order failed for %s %s %s: %s", side, qty, ticker, exc)
        return OrderResult(
            alpaca_order_id="",
            ticker=ticker.upper(),
            side=side.lower(),
            qty=qty,
            status="rejected",
            error=str(exc),
        )


async def get_order(alpaca_order_id: str) -> Optional[OrderResult]:
    """Fetch the current status of an order by its Alpaca order ID."""
    import asyncio

    def _fetch():
        client = _get_client()
        from alpaca.trading.requests import GetOrderByIdRequest
        order = client.get_order_by_id(alpaca_order_id)
        return order

    try:
        order = await asyncio.to_thread(_fetch)
        return OrderResult(
            alpaca_order_id=str(order.id),
            ticker=str(order.symbol),
            side=str(order.side.value) if hasattr(order.side, "value") else str(order.side),
            qty=float(order.qty or 0),
            status=str(order.status.value) if hasattr(order.status, "value") else str(order.status),
            submitted_at=order.submitted_at,
            filled_at=order.filled_at,
            filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
        )
    except Exception as exc:
        logger.error("Alpaca get_order failed for %s: %s", alpaca_order_id, exc)
        return None


async def get_account_positions() -> list[AlpacaPosition]:
    """Return all current Alpaca paper positions."""
    import asyncio

    def _fetch():
        client = _get_client()
        return client.get_all_positions()

    try:
        positions = await asyncio.to_thread(_fetch)
        return [
            AlpacaPosition(
                ticker=str(p.symbol),
                qty=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price or 0),
                market_value=float(p.market_value or 0),
                unrealized_pl=float(p.unrealized_pl or 0),
                unrealized_plpc=float(p.unrealized_plpc or 0) * 100,
            )
            for p in positions
        ]
    except Exception as exc:
        logger.error("Alpaca get_account_positions failed: %s", exc)
        return []


def alpaca_configured() -> bool:
    """Returns True if Alpaca credentials are present in the environment."""
    return _is_configured()
