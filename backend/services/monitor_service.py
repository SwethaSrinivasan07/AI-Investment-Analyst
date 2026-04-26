"""
Daily portfolio monitor service.

For each user with portfolio positions, this service:
1. Fetches live prices and recent news for every holding
2. Detects significant price moves (>= PRICE_MOVE_THRESHOLD)
3. Asks Claude for proactive buy/sell/hold recommendations across the whole portfolio
4. Persists PortfolioAlert rows so the frontend can surface them

Called by APScheduler daily at 07:00 local server time.
Never raises — all errors are swallowed and logged so other users' runs continue.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import anthropic
from sqlalchemy import select

from models.database import AsyncSessionLocal, settings
from models.models import PortfolioAlert, PortfolioPosition, User

logger = logging.getLogger(__name__)

PRICE_MOVE_THRESHOLD = 3.0   # % daily move that triggers a price-move alert
MAX_ALERTS_PER_RUN = 10      # cap per user so inbox doesn't explode


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _fetch_price(ticker: str) -> dict:
    from services.data_fetcher import get_price_history
    return await asyncio.to_thread(get_price_history, ticker, "5d")


async def _fetch_news(ticker: str) -> list[str]:
    from services.data_fetcher import get_news_sentiment
    try:
        result = await asyncio.to_thread(get_news_sentiment, ticker)
        headlines = result.get("headlines") or []
        return [h.get("title", "") for h in headlines[:3] if h.get("title")]
    except Exception:
        return []


async def _get_ai_recommendations(snapshot: list[dict]) -> list[dict]:
    """
    Ask Claude for proactive trade recommendations across the portfolio.
    Returns a list of {ticker, action, rationale, severity}.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    lines = []
    for p in snapshot:
        news_text = "; ".join(p.get("headlines", [])[:2]) or "No recent news"
        lines.append(
            f"- {p['ticker']}: gain {p['gain_loss_pct']:+.1f}%, "
            f"1D {p['price_change_1d_pct']:+.1f}%, "
            f"RSI {p.get('rsi', 'N/A')}, "
            f"news: {news_text}"
        )

    prompt = (
        "You are a proactive portfolio analyst reviewing a client's holdings each morning.\n"
        "Based on the data below, identify positions that warrant action today.\n"
        "For each actionable position, output ONE item in this JSON array:\n"
        '  [{"ticker":"X","action":"Buy more"|"Trim"|"Sell"|"Watch","rationale":"1 sentence","severity":"action"|"warning"|"info"}]\n'
        "Only include tickers where action is genuinely warranted — omit calm, hold-worthy positions.\n"
        "Maximum 4 recommendations. If nothing warrants action, return [].\n\n"
        "Portfolio:\n" + "\n".join(lines) + "\n\nJSON array only:"
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.splitlines() if not l.startswith("```")).strip()
        return json.loads(raw)
    except Exception as exc:
        logger.warning("AI recommendations failed: %s", exc)
        return []


def _make_alert(
    user_id: str,
    ticker: Optional[str],
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    data: Optional[dict] = None,
) -> PortfolioAlert:
    return PortfolioAlert(
        user_id=user_id,
        ticker=ticker,
        alert_type=alert_type,
        severity=severity,
        title=title,
        message=message,
        data=data or {},
    )


# ---------------------------------------------------------------------------
# Per-user monitor run
# ---------------------------------------------------------------------------

async def _monitor_user(user_id: str, positions: list[PortfolioPosition]) -> list[PortfolioAlert]:
    """Run a full monitoring pass for one user. Returns alerts to persist."""
    tickers = [p.ticker for p in positions]

    # Fetch all prices + news concurrently
    price_tasks = [_fetch_price(t) for t in tickers]
    news_tasks  = [_fetch_news(t)  for t in tickers]
    results = await asyncio.gather(*price_tasks, *news_tasks, return_exceptions=True)

    price_map: dict[str, dict] = {}
    news_map:  dict[str, list[str]] = {}
    for ticker, res in zip(tickers, results[: len(tickers)]):
        price_map[ticker] = res if not isinstance(res, Exception) else {}
    for ticker, res in zip(tickers, results[len(tickers) :]):
        news_map[ticker] = res if not isinstance(res, list) or isinstance(res, Exception) else res

    alerts: list[PortfolioAlert] = []

    snapshot: list[dict] = []
    for pos in positions:
        pd = price_map.get(pos.ticker, {})
        current_price: float = pd.get("current_price") or 0.0
        change_1d: float     = pd.get("price_change_1d_pct") or 0.0
        rsi: Optional[float] = pd.get("rsi_14")

        market_value = pos.shares * current_price
        cost_value   = pos.shares * pos.cost_basis
        gain_loss_pct = ((market_value - cost_value) / cost_value * 100) if cost_value else 0.0

        snapshot.append({
            "ticker": pos.ticker,
            "current_price": current_price,
            "price_change_1d_pct": change_1d,
            "gain_loss_pct": gain_loss_pct,
            "rsi": round(rsi, 1) if rsi else None,
            "headlines": news_map.get(pos.ticker, []),
        })

        # Price-move alert
        if abs(change_1d) >= PRICE_MOVE_THRESHOLD:
            direction = "surged" if change_1d > 0 else "dropped"
            severity  = "action" if abs(change_1d) >= 5.0 else "warning"
            alerts.append(_make_alert(
                user_id=user_id,
                ticker=pos.ticker,
                alert_type="price_move",
                severity=severity,
                title=f"{pos.ticker} {direction} {abs(change_1d):.1f}% today",
                message=(
                    f"{pos.ticker} moved {change_1d:+.1f}% today. "
                    f"Your position is {'up' if gain_loss_pct >= 0 else 'down'} "
                    f"{abs(gain_loss_pct):.1f}% overall. "
                    + (f"Recent news: {news_map[pos.ticker][0]}" if news_map.get(pos.ticker) else "No recent news available.")
                ),
                data={"price_change_1d_pct": change_1d, "gain_loss_pct": gain_loss_pct, "current_price": current_price},
            ))

        # RSI extremes
        if rsi is not None:
            if rsi > 75:
                alerts.append(_make_alert(
                    user_id=user_id,
                    ticker=pos.ticker,
                    alert_type="signal",
                    severity="warning",
                    title=f"{pos.ticker} RSI overbought ({rsi:.0f})",
                    message=f"{pos.ticker}'s RSI has reached {rsi:.0f}, signalling the stock may be overbought. Consider whether to trim.",
                    data={"rsi": rsi},
                ))
            elif rsi < 28:
                alerts.append(_make_alert(
                    user_id=user_id,
                    ticker=pos.ticker,
                    alert_type="signal",
                    severity="info",
                    title=f"{pos.ticker} RSI oversold ({rsi:.0f})",
                    message=f"{pos.ticker}'s RSI has fallen to {rsi:.0f}, signalling a potential buying opportunity.",
                    data={"rsi": rsi},
                ))

    # AI proactive recommendations
    if snapshot:
        recs = await _get_ai_recommendations(snapshot)
        for rec in recs[:4]:
            ticker = rec.get("ticker", "")
            action = rec.get("action", "Watch")
            rationale = rec.get("rationale", "")
            severity = rec.get("severity", "info")
            alerts.append(_make_alert(
                user_id=user_id,
                ticker=ticker or None,
                alert_type="opportunity",
                severity=severity,
                title=f"AI signal: {action} {ticker}" if ticker else f"AI signal: {action}",
                message=rationale,
                data={"action": action, "ticker": ticker},
            ))

    return alerts[:MAX_ALERTS_PER_RUN]


# ---------------------------------------------------------------------------
# Public entry point — called by APScheduler
# ---------------------------------------------------------------------------

async def run_daily_monitor() -> None:
    """
    Entry point for the daily monitoring job.
    Iterates over all users who have portfolio positions and generates alerts.
    """
    logger.info("[Monitor] Daily portfolio monitor starting...")
    start = datetime.utcnow()

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(PortfolioPosition))
            all_positions: list[PortfolioPosition] = list(result.scalars().all())
    except Exception as exc:
        logger.error("[Monitor] Failed to load positions: %s", exc)
        return

    if not all_positions:
        logger.info("[Monitor] No portfolio positions found — nothing to monitor.")
        return

    # Group by user
    by_user: dict[str, list[PortfolioPosition]] = {}
    for pos in all_positions:
        by_user.setdefault(pos.user_id, []).append(pos)

    total_alerts = 0
    for user_id, positions in by_user.items():
        try:
            alerts = await _monitor_user(user_id, positions)
            if alerts:
                async with AsyncSessionLocal() as db:
                    for alert in alerts:
                        db.add(alert)
                    await db.commit()
                total_alerts += len(alerts)
                logger.info("[Monitor] Saved %d alerts for user %s", len(alerts), user_id)
        except Exception as exc:
            logger.error("[Monitor] Failed for user %s: %s", user_id, exc, exc_info=True)

    elapsed = (datetime.utcnow() - start).total_seconds()
    logger.info("[Monitor] Done. %d alerts across %d users in %.1fs.", total_alerts, len(by_user), elapsed)
