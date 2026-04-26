"""
Portfolio API endpoints:
- GET  /api/portfolio                    — returns portfolio with live prices + AI signals
- POST /api/portfolio/seed               — seeds portfolio from data/dummy_portfolio.json
- POST /api/portfolio/import             — import positions from brokerage CSV
- POST /api/portfolio/positions          — add a position
- DELETE /api/portfolio/positions/{id}  — remove a position
- GET  /api/portfolio/alerts             — get unread alerts for the user
- POST /api/portfolio/alerts/{id}/read  — mark an alert as read
- POST /api/portfolio/alerts/run        — trigger a monitor run immediately (dev/demo)
- GET  /api/portfolio/orders             — order history
- POST /api/portfolio/orders             — place a paper trade via Alpaca
- GET  /api/portfolio/alpaca/status      — whether Alpaca is configured
"""

import asyncio
import csv
import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from models.database import get_db, settings
from models.models import PortfolioAlert, PortfolioOrder, PortfolioPosition, User
from services.data_fetcher import get_news_sentiment, get_price_history

router = APIRouter()
logger = logging.getLogger(__name__)

# Path to the dummy portfolio JSON (repo_root/data/dummy_portfolio.json)
# This file lives at backend/api/portfolio.py, so parent.parent = repo root
_DUMMY_PORTFOLIO_PATH = Path(__file__).parent.parent.parent / "data" / "dummy_portfolio.json"


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class AddPositionRequest(BaseModel):
    ticker: str
    shares: float
    cost_basis: float


class PositionOut(BaseModel):
    id: str
    ticker: str
    company_name: Optional[str]
    shares: float
    cost_basis: float
    current_price: float
    market_value: float
    cost_value: float
    gain_loss: float
    gain_loss_pct: float
    price_change_1d_pct: float
    signal: str
    signal_rationale: str
    added_at: datetime

    class Config:
        from_attributes = True


class PortfolioSummary(BaseModel):
    total_value: float
    total_cost: float
    total_gain_loss: float
    total_gain_loss_pct: float
    position_count: int


class PortfolioResponse(BaseModel):
    positions: list[PositionOut]
    summary: PortfolioSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_dummy_portfolio() -> list[dict]:
    """Load positions from the bundled dummy_portfolio.json."""
    with open(_DUMMY_PORTFOLIO_PATH) as fh:
        return json.load(fh)


async def _seed_positions(user_id: str, db: AsyncSession) -> list[PortfolioPosition]:
    """Insert dummy portfolio rows for the user and return them."""
    raw = _load_dummy_portfolio()
    positions: list[PortfolioPosition] = []
    for entry in raw:
        added_at = datetime.strptime(entry["added_date"], "%Y-%m-%d")
        pos = PortfolioPosition(
            user_id=user_id,
            ticker=entry["ticker"],
            shares=float(entry["shares"]),
            cost_basis=float(entry["cost_basis"]),
            added_at=added_at,
        )
        db.add(pos)
        positions.append(pos)
    await db.commit()
    # Refresh all to get generated IDs
    for pos in positions:
        await db.refresh(pos)
    return positions


async def _fetch_price(ticker: str) -> dict:
    """Wrap synchronous get_price_history in a thread."""
    return await asyncio.to_thread(get_price_history, ticker, "3mo")


async def _get_ai_signals(
    portfolio_snapshot: list[dict],
    news_data: dict[str, list[str]],
) -> dict[str, dict]:
    """
    Call Claude once with the full portfolio (including recent news headlines) and
    return a dict keyed by ticker.
    Each value: {"signal": "Hold"|"Trim"|"Add", "rationale": str}
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = (
        "You are a portfolio analyst. Given this portfolio snapshot with recent news, "
        "provide a signal (Hold/Trim/Add) and a ONE-sentence rationale for each position. "
        "Base your signal on: gain/loss level, recent price momentum, AND the news context provided.\n\n"
        "Portfolio positions:\n"
    )
    for pos in portfolio_snapshot:
        ticker = pos["ticker"]
        headlines = news_data.get(ticker, [])
        news_text = "; ".join(headlines[:3]) if headlines else "No recent news"
        prompt += (
            f"\n{ticker} ({pos.get('company_name', ticker)}): "
            f"Gain {pos['gain_loss_pct']:+.1f}%, "
            f"1D change {pos['price_change_1d_pct']:+.1f}%, "
            f"Current ${pos['current_price']:.2f}\n"
            f"  Recent news: {news_text}\n"
        )
    prompt += "\nReturn ONLY a JSON array: [{\"ticker\": \"AAPL\", \"signal\": \"Hold\", \"rationale\": \"...\"}, ...]"

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        signals_list: list[dict] = json.loads(raw_text)
        return {
            item["ticker"]: {
                "signal": item.get("signal", "Hold"),
                "rationale": item.get("rationale", ""),
            }
            for item in signals_list
        }
    except Exception as exc:
        logger.error(f"_get_ai_signals error: {exc}", exc_info=True)
        # Fall back: return Hold for all
        return {
            pos["ticker"]: {"signal": "Hold", "rationale": "AI signal unavailable."}
            for pos in portfolio_snapshot
        }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=PortfolioResponse)
async def get_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the user's portfolio with live prices and AI signals.
    Auto-seeds from dummy_portfolio.json if the user has no positions.
    """
    # 1. Load positions from DB
    result = await db.execute(
        select(PortfolioPosition).where(PortfolioPosition.user_id == current_user.id)
    )
    positions: list[PortfolioPosition] = list(result.scalars().all())

    # 2. Auto-seed if empty
    if not positions:
        logger.info(f"Auto-seeding portfolio for user {current_user.id}")
        positions = await _seed_positions(current_user.id, db)

    # Build a lookup for company names from the dummy file (best effort)
    dummy_company_names: dict[str, str] = {}
    try:
        for entry in _load_dummy_portfolio():
            dummy_company_names[entry["ticker"]] = entry.get("company_name", "")
    except Exception:
        pass

    # 3. Fetch live prices AND news for all tickers concurrently
    tickers = [pos.ticker for pos in positions]
    price_tasks = [_fetch_price(ticker) for ticker in tickers]
    news_tasks = [asyncio.to_thread(get_news_sentiment, ticker) for ticker in tickers]
    all_results = await asyncio.gather(*price_tasks, *news_tasks, return_exceptions=True)

    price_results = all_results[: len(tickers)]
    news_results_raw = all_results[len(tickers) :]

    price_map: dict[str, dict] = {}
    for ticker, res in zip(tickers, price_results):
        if isinstance(res, Exception):
            logger.error(f"Price fetch failed for {ticker}: {res}")
            price_map[ticker] = {"current_price": 0.0, "price_change_1d_pct": 0.0}
        else:
            price_map[ticker] = res

    news_data: dict[str, list[str]] = {}
    for ticker, res in zip(tickers, news_results_raw):
        if isinstance(res, Exception):
            logger.warning(f"News fetch failed for {ticker}: {res}")
            news_data[ticker] = []
        else:
            headlines = [h.get("title", "") for h in (res.get("headlines") or [])[:3]]
            news_data[ticker] = [h for h in headlines if h]

    # 4. Compute per-position metrics
    enriched: list[dict] = []
    for pos in positions:
        price_data = price_map.get(pos.ticker, {})
        current_price: float = price_data.get("current_price", 0.0) or 0.0
        price_change_1d: float = price_data.get("price_change_1d_pct", 0.0) or 0.0

        market_value = pos.shares * current_price
        cost_value = pos.shares * pos.cost_basis
        gain_loss = market_value - cost_value
        gain_loss_pct = (gain_loss / cost_value * 100) if cost_value else 0.0

        enriched.append({
            "id": pos.id,
            "ticker": pos.ticker,
            "company_name": dummy_company_names.get(pos.ticker),
            "shares": pos.shares,
            "cost_basis": pos.cost_basis,
            "current_price": round(current_price, 4),
            "market_value": round(market_value, 2),
            "cost_value": round(cost_value, 2),
            "gain_loss": round(gain_loss, 2),
            "gain_loss_pct": round(gain_loss_pct, 2),
            "price_change_1d_pct": round(price_change_1d, 2),
            "signal": "Hold",          # filled in after Claude call
            "signal_rationale": "",    # filled in after Claude call
            "added_at": pos.added_at,
        })

    # 5. Run a SINGLE Claude call for all positions
    portfolio_snapshot = [
        {
            "ticker": p["ticker"],
            "company_name": p["company_name"],
            "shares": p["shares"],
            "cost_basis": p["cost_basis"],
            "current_price": p["current_price"],
            "gain_loss_pct": p["gain_loss_pct"],
            "price_change_1d_pct": p["price_change_1d_pct"],
        }
        for p in enriched
    ]
    ai_signals = await _get_ai_signals(portfolio_snapshot, news_data)

    for p in enriched:
        sig = ai_signals.get(p["ticker"], {"signal": "Hold", "rationale": ""})
        p["signal"] = sig["signal"]
        p["signal_rationale"] = sig["rationale"]

    # 6. Portfolio-level summary
    total_value = sum(p["market_value"] for p in enriched)
    total_cost = sum(p["cost_value"] for p in enriched)
    total_gain_loss = total_value - total_cost
    total_gain_loss_pct = (total_gain_loss / total_cost * 100) if total_cost else 0.0

    summary = PortfolioSummary(
        total_value=round(total_value, 2),
        total_cost=round(total_cost, 2),
        total_gain_loss=round(total_gain_loss, 2),
        total_gain_loss_pct=round(total_gain_loss_pct, 2),
        position_count=len(enriched),
    )

    position_outs = [PositionOut(**p) for p in enriched]
    return PortfolioResponse(positions=position_outs, summary=summary)


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_portfolio(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Seeds the user's portfolio from data/dummy_portfolio.json.
    Only seeds if the user currently has no positions.
    """
    result = await db.execute(
        select(PortfolioPosition).where(PortfolioPosition.user_id == current_user.id)
    )
    existing = result.scalars().first()
    if existing:
        return {"detail": "Portfolio already has positions. Seed skipped."}

    positions = await _seed_positions(current_user.id, db)
    return {"detail": f"Seeded {len(positions)} positions from dummy portfolio."}


@router.post("/positions", response_model=PositionOut, status_code=status.HTTP_201_CREATED)
async def add_position(
    req: AddPositionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new position to the user's portfolio."""
    # Validate ticker by fetching live price
    try:
        price_data = await _fetch_price(req.ticker.upper())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not fetch price data for ticker '{req.ticker}': {exc}",
        )

    pos = PortfolioPosition(
        user_id=current_user.id,
        ticker=req.ticker.upper(),
        shares=req.shares,
        cost_basis=req.cost_basis,
    )
    db.add(pos)
    await db.commit()
    await db.refresh(pos)

    current_price: float = price_data.get("current_price", 0.0) or 0.0
    price_change_1d: float = price_data.get("price_change_1d_pct", 0.0) or 0.0
    market_value = pos.shares * current_price
    cost_value = pos.shares * pos.cost_basis
    gain_loss = market_value - cost_value
    gain_loss_pct = (gain_loss / cost_value * 100) if cost_value else 0.0

    return PositionOut(
        id=pos.id,
        ticker=pos.ticker,
        company_name=None,
        shares=pos.shares,
        cost_basis=pos.cost_basis,
        current_price=round(current_price, 4),
        market_value=round(market_value, 2),
        cost_value=round(cost_value, 2),
        gain_loss=round(gain_loss, 2),
        gain_loss_pct=round(gain_loss_pct, 2),
        price_change_1d_pct=round(price_change_1d, 2),
        signal="Hold",
        signal_rationale="Position just added.",
        added_at=pos.added_at,
    )


@router.delete("/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    position_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a position from the user's portfolio."""
    result = await db.execute(
        select(PortfolioPosition).where(
            PortfolioPosition.id == position_id,
            PortfolioPosition.user_id == current_user.id,
        )
    )
    pos = result.scalar_one_or_none()
    if pos is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")

    await db.delete(pos)
    await db.commit()


# ---------------------------------------------------------------------------
# CSV Import
# ---------------------------------------------------------------------------

def _parse_csv(content: str) -> list[dict]:
    """
    Parse a brokerage CSV into a list of {ticker, shares, cost_basis} dicts.
    Handles three formats:
      1. Standard:   Symbol/Ticker, Shares/Quantity, Cost/CostBasis/AvgCost
      2. Schwab:     Symbol, Quantity, Cost Basis (total — divided by qty)
      3. Robinhood:  symbol, quantity, average_buy_price
    """
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        raise ValueError("CSV appears to be empty.")

    # Normalise header names to lowercase-stripped
    fieldnames = [f.strip().lower().replace(" ", "_") for f in (reader.fieldnames or [])]

    def col(row: dict, *candidates: str) -> Optional[str]:
        for c in candidates:
            for k, v in row.items():
                if k.strip().lower().replace(" ", "_") == c and v and v.strip():
                    return v.strip()
        return None

    parsed: list[dict] = []
    for row in rows:
        ticker  = col(row, "symbol", "ticker")
        shares_s = col(row, "quantity", "shares", "qty")
        # Cost basis: Robinhood gives per-share price, Schwab gives total cost
        cost_s   = col(row, "average_buy_price", "cost_basis_per_share", "avg_cost", "average_cost")
        if not cost_s:
            # Schwab-style: total cost basis divided by qty
            total_cost_s = col(row, "cost_basis", "total_cost", "cost")
            if total_cost_s and shares_s:
                try:
                    cost_s = str(float(total_cost_s.replace("$", "").replace(",", "")) /
                                 float(shares_s.replace(",", "")))
                except Exception:
                    cost_s = None

        if not ticker or not shares_s or not cost_s:
            continue
        # Skip header-like rows or cash rows
        if ticker.upper() in ("SYMBOL", "TICKER", "CASH", "--"):
            continue
        try:
            shares    = float(shares_s.replace(",", ""))
            cost_basis = float(cost_s.replace("$", "").replace(",", ""))
            if shares <= 0 or cost_basis <= 0:
                continue
            parsed.append({"ticker": ticker.upper(), "shares": shares, "cost_basis": cost_basis})
        except Exception:
            continue

    if not parsed:
        raise ValueError("No valid positions found in CSV. Check the format.")
    return parsed


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_portfolio_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Replace the user's portfolio with positions parsed from a brokerage CSV.
    Accepts Schwab, Robinhood, or a simple Symbol/Shares/CostBasis format.
    """
    content_bytes = await file.read()
    try:
        content = content_bytes.decode("utf-8", errors="replace")
        positions_data = _parse_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to parse CSV: {exc}")

    # Delete existing positions
    result = await db.execute(
        select(PortfolioPosition).where(PortfolioPosition.user_id == current_user.id)
    )
    for pos in result.scalars().all():
        await db.delete(pos)

    # Insert new positions
    new_positions = []
    for entry in positions_data:
        pos = PortfolioPosition(
            user_id=current_user.id,
            ticker=entry["ticker"],
            shares=entry["shares"],
            cost_basis=entry["cost_basis"],
        )
        db.add(pos)
        new_positions.append(pos)

    await db.commit()
    return {"detail": f"Imported {len(new_positions)} positions from CSV.", "count": len(new_positions)}


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class AlertOut(BaseModel):
    id: str
    ticker: Optional[str]
    alert_type: str
    severity: str
    title: str
    message: str
    data: Optional[dict]
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/alerts", response_model=list[AlertOut])
async def get_alerts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    unread_only: bool = False,
):
    """Return alerts for the current user, newest first."""
    query = select(PortfolioAlert).where(PortfolioAlert.user_id == current_user.id)
    if unread_only:
        query = query.where(PortfolioAlert.read == False)  # noqa: E712
    query = query.order_by(desc(PortfolioAlert.created_at)).limit(limit)
    result = await db.execute(query)
    return [AlertOut.model_validate(a) for a in result.scalars().all()]


@router.post("/alerts/{alert_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_alert_read(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single alert as read."""
    result = await db.execute(
        select(PortfolioAlert).where(
            PortfolioAlert.id == alert_id,
            PortfolioAlert.user_id == current_user.id,
        )
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert.read = True
    await db.commit()


@router.post("/alerts/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_alerts_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all of the user's alerts as read."""
    result = await db.execute(
        select(PortfolioAlert).where(
            PortfolioAlert.user_id == current_user.id,
            PortfolioAlert.read == False,  # noqa: E712
        )
    )
    for alert in result.scalars().all():
        alert.read = True
    await db.commit()


@router.post("/alerts/run", status_code=status.HTTP_202_ACCEPTED)
async def trigger_monitor_run(
    current_user: User = Depends(get_current_user),
):
    """
    Trigger an immediate monitoring run for the current user (demo / dev endpoint).
    Runs in background so the response returns immediately.
    """
    import asyncio
    from services.monitor_service import _monitor_user

    async def _run():
        try:
            async with AsyncSessionLocal() as db:  # noqa: F821
                from models.database import AsyncSessionLocal as _ASL
                async with _ASL() as db2:
                    result = await db2.execute(
                        select(PortfolioPosition).where(PortfolioPosition.user_id == current_user.id)
                    )
                    positions = list(result.scalars().all())
            if positions:
                from models.database import AsyncSessionLocal as _ASL2
                alerts = await _monitor_user(current_user.id, positions)
                async with _ASL2() as db3:
                    for alert in alerts:
                        db3.add(alert)
                    await db3.commit()
        except Exception as exc:
            logger.error("Trigger monitor run failed: %s", exc, exc_info=True)

    asyncio.create_task(_run())
    return {"detail": "Monitor run triggered. Alerts will appear shortly."}


# ---------------------------------------------------------------------------
# Orders (Alpaca paper trading)
# ---------------------------------------------------------------------------

class PlaceOrderRequest(BaseModel):
    ticker: str
    side: str      # buy | sell
    qty: float
    rationale: str = ""


class OrderOut(BaseModel):
    id: str
    ticker: str
    side: str
    qty: float
    status: str
    alpaca_order_id: Optional[str]
    filled_price: Optional[float]
    rationale: Optional[str]
    created_at: datetime
    filled_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/alpaca/status")
async def alpaca_status(_: User = Depends(get_current_user)):
    """Returns whether Alpaca paper trading is configured."""
    from services.alpaca_service import alpaca_configured
    return {"configured": alpaca_configured(), "mode": "paper"}


@router.get("/orders", response_model=list[OrderOut])
async def get_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's order history, newest first."""
    result = await db.execute(
        select(PortfolioOrder)
        .where(PortfolioOrder.user_id == current_user.id)
        .order_by(desc(PortfolioOrder.created_at))
        .limit(50)
    )
    return [OrderOut.model_validate(o) for o in result.scalars().all()]


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def place_order(
    req: PlaceOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Place a paper trade via Alpaca and record it in the DB.
    Requires ALPACA_API_KEY + ALPACA_SECRET_KEY in backend/.env.
    """
    from services.alpaca_service import alpaca_configured, place_order as alpaca_place

    if req.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")
    if req.side.lower() not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="side must be 'buy' or 'sell'")

    # If Alpaca is not configured, record the order as pending (for demo without keys)
    if not alpaca_configured():
        order = PortfolioOrder(
            user_id=current_user.id,
            ticker=req.ticker.upper(),
            side=req.side.lower(),
            qty=req.qty,
            status="pending",
            rationale=req.rationale,
            source="ai_signal",
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)
        return OrderOut.model_validate(order)

    # Submit to Alpaca
    result = await alpaca_place(
        ticker=req.ticker,
        side=req.side,
        qty=req.qty,
        rationale=req.rationale,
    )

    order = PortfolioOrder(
        user_id=current_user.id,
        ticker=result.ticker,
        side=result.side,
        qty=result.qty,
        status=result.status,
        alpaca_order_id=result.alpaca_order_id or None,
        filled_price=result.filled_avg_price,
        rationale=req.rationale,
        source="ai_signal",
        filled_at=result.filled_at,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    if result.error:
        logger.warning("Alpaca order error for %s: %s", req.ticker, result.error)

    return OrderOut.model_validate(order)
