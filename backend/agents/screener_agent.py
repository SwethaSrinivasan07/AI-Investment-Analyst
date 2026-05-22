"""
ScreenerAgent: screens tickers by strategy and sector, returns ranked picks.
"""

import asyncio
import logging
import time
from typing import Any

from services.data_fetcher import (
    compute_dividend_score,
    compute_growth_score,
    compute_momentum_score,
    compute_value_score,
    get_fundamentals,
    get_news_sentiment,
    get_price_history,
    get_sector_peers,
)

logger = logging.getLogger(__name__)


class ScreenerAgent:
    """
    Screens S&P 500 peers in a given sector by strategy, returns ranked picks
    with full data packages.
    """

    STRATEGY_SCORE_MAP = {
        "momentum": compute_momentum_score,
        "value": compute_value_score,
        "growth": compute_growth_score,
        "dividend": compute_dividend_score,
    }

    def screen(
        self, strategy: str, sector: str, num_picks: int = 3
    ) -> list[dict[str, Any]]:
        """
        Synchronous screening method.

        Returns a ranked list of dicts:
        {
            ticker, company_name, score, signals, data_package
        }
        """
        strategy = strategy.lower()
        if strategy not in self.STRATEGY_SCORE_MAP:
            raise ValueError(
                f"Unknown strategy '{strategy}'. "
                f"Must be one of: {list(self.STRATEGY_SCORE_MAP.keys())}"
            )

        score_fn = self.STRATEGY_SCORE_MAP[strategy]
        peers = get_sector_peers(sector)

        results = []
        for ticker in peers:
            try:
                # Fetch all data ONCE per ticker (avoids duplicate yfinance calls)
                fundamentals = get_fundamentals(ticker)
                price_data = get_price_history(ticker, period="1y")
                news = get_news_sentiment(ticker)

                # Compute strategy score from pre-fetched data
                score = _score_from_data(strategy, sector, fundamentals, price_data)

                if score <= 0:
                    time.sleep(0.3)  # still throttle even on skip
                    continue

                data_package = {
                    **fundamentals,
                    "price_history": {
                        "current_price": price_data.get("current_price"),
                        "price_change_1d_pct": price_data.get("price_change_1d_pct"),
                        "price_change_1m_pct": price_data.get("price_change_1m_pct"),
                        "price_change_3m_pct": price_data.get("price_change_3m_pct"),
                        "price_change_6m_pct": price_data.get("price_change_6m_pct"),
                        "price_change_1y_pct": price_data.get("price_change_1y_pct"),
                        "ma_50": price_data.get("ma_50"),
                        "ma_200": price_data.get("ma_200"),
                        "rsi_14": price_data.get("rsi_14"),
                    },
                    "news_sentiment": {
                        "sentiment_score": news.get("sentiment_score"),
                        "headlines": news.get("headlines", [])[:5],
                    },
                    "strategy": strategy,
                    "sector": sector,
                    "score": score,
                }

                signals = _build_signals(strategy, fundamentals, price_data, score)

                results.append({
                    "ticker": ticker,
                    "company_name": fundamentals.get("company_name") or ticker,
                    "score": score,
                    "signals": signals,
                    "data_package": data_package,
                })

            except Exception as e:
                logger.warning(f"Screener skipping {ticker}: {e}")

            finally:
                # Throttle: 0.4s between tickers to avoid Yahoo Finance 429s
                time.sleep(0.4)

        # Sort by score descending, return top N
        results.sort(key=lambda x: x["score"], reverse=True)
        picks = results[:num_picks]

        # ── Fallback: if yfinance failed for every ticker (rate-limit on cloud),
        #    return synthetic stubs so the pipeline can still run. The Research
        #    Agent fetches live data via its own tool calls.
        if not picks:
            logger.warning(
                "Screener got 0 results (likely yfinance rate-limit). "
                "Using hardcoded fallback tickers."
            )
            fallback_map: dict[str, list[str]] = {
                "technology": ["NVDA", "MSFT", "AAPL"],
                "healthcare": ["LLY", "JNJ", "ABBV"],
                "financials": ["JPM", "BAC", "GS"],
                "energy": ["XOM", "CVX", "COP"],
                "consumer discretionary": ["AMZN", "TSLA", "MCD"],
                "consumer staples": ["PG", "KO", "PEP"],
                "industrials": ["HON", "CAT", "UPS"],
                "utilities": ["NEE", "DUK", "SO"],
                "real estate": ["PLD", "AMT", "EQIX"],
                "materials": ["LIN", "APD", "SHW"],
                "communication services": ["GOOGL", "META", "NFLX"],
            }
            fallback_tickers = fallback_map.get(sector.lower(), ["AAPL", "MSFT", "GOOGL"])
            for fb_ticker in fallback_tickers[:num_picks]:
                picks.append({
                    "ticker": fb_ticker,
                    "company_name": fb_ticker,
                    "score": 50.0,
                    "signals": [f"Fallback pick — live data fetch failed for sector '{sector}'"],
                    "data_package": {
                        "ticker": fb_ticker,
                        "company_name": fb_ticker,
                        "strategy": strategy,
                        "sector": sector,
                        "score": 50.0,
                    },
                })

        return picks

    async def screen_async(
        self, strategy: str, sector: str, num_picks: int = 3
    ) -> list[dict[str, Any]]:
        """Async wrapper — runs synchronous screen() in a thread."""
        return await asyncio.to_thread(self.screen, strategy, sector, num_picks)


def _score_from_data(
    strategy: str,
    sector: str,
    fundamentals: dict,
    price_data: dict,
) -> float:
    """
    Compute strategy score from pre-fetched data dicts.
    Avoids re-calling yfinance (which the original score functions do internally).
    """
    try:
        if strategy == "momentum":
            m1 = price_data.get("price_change_1m_pct", 0) or 0
            m3 = price_data.get("price_change_3m_pct", 0) or 0
            m6 = price_data.get("price_change_6m_pct", 0) or 0
            rsi = price_data.get("rsi_14", 50) or 50

            def norm(r):
                return (max(-50, min(50, r)) + 50) / 100 * 100

            if 55 <= rsi <= 70:
                rsi_score = 90.0
            elif 45 <= rsi < 55:
                rsi_score = 60.0
            elif 70 < rsi <= 80:
                rsi_score = 70.0
            elif rsi > 80:
                rsi_score = 40.0
            else:
                rsi_score = 30.0

            return round(min(100, max(0,
                norm(m1) * 0.30 + norm(m3) * 0.30 + norm(m6) * 0.20 + rsi_score * 0.20
            )), 2)

        elif strategy == "value":
            pe = fundamentals.get("pe_ratio")
            pb = fundamentals.get("pb_ratio")
            ev_ebitda = fundamentals.get("ev_ebitda")
            fcf_yield = fundamentals.get("fcf_yield") or 0
            ps = fundamentals.get("ps_ratio")

            def spe(v):
                if v is None or v <= 0: return 50.0
                if v < 12: return 95.0
                if v < 18: return 80.0
                if v < 25: return 60.0
                if v < 35: return 40.0
                return 20.0

            def spb(v):
                if v is None or v <= 0: return 50.0
                if v < 1.0: return 95.0
                if v < 2.0: return 80.0
                if v < 3.5: return 60.0
                if v < 5.0: return 40.0
                return 20.0

            def sev(v):
                if v is None or v <= 0: return 50.0
                if v < 8: return 95.0
                if v < 12: return 75.0
                if v < 18: return 55.0
                if v < 25: return 35.0
                return 15.0

            def sfcf(v):
                if v is None: return 50.0
                if v > 8: return 95.0
                if v > 5: return 80.0
                if v > 3: return 60.0
                if v > 0: return 40.0
                return 20.0

            def sps(v):
                if v is None or v <= 0: return 50.0
                if v < 1.0: return 95.0
                if v < 2.5: return 75.0
                if v < 5.0: return 55.0
                if v < 10.0: return 35.0
                return 15.0

            return round(min(100, max(0,
                spe(pe) * 0.25 + spb(pb) * 0.20 + sev(ev_ebitda) * 0.20 +
                sfcf(fcf_yield) * 0.20 + sps(ps) * 0.15
            )), 2)

        elif strategy == "growth":
            rev_growth = fundamentals.get("revenue_growth_yoy") or 0
            gross_margin = fundamentals.get("gross_margin") or 0
            op_margin = fundamentals.get("operating_margin") or 0
            m3 = price_data.get("price_change_3m_pct", 0) or 0

            def srg(g):
                if g > 40: return 95.0
                if g > 25: return 85.0
                if g > 15: return 70.0
                if g > 8: return 55.0
                if g > 0: return 40.0
                return 20.0

            def sm(v, thresholds):
                for t, s in thresholds:
                    if v >= t: return s
                return 20.0

            return round(min(100, max(0,
                srg(rev_growth) * 0.35 +
                sm(gross_margin, [(70,95),(50,80),(35,65),(20,45),(0,30)]) * 0.25 +
                sm(op_margin,    [(30,95),(20,80),(12,65),(5,45),(0,30)]) * 0.20 +
                max(0, min(100, (m3 + 30) / 60 * 100)) * 0.20
            )), 2)

        elif strategy == "dividend":
            div_yield = fundamentals.get("dividend_yield") or 0
            payout_ratio = fundamentals.get("payout_ratio") or 0
            debt_to_equity = fundamentals.get("debt_to_equity") or 0
            change_1y = abs(price_data.get("price_change_1y_pct", 0) or 0)

            def sy(y):
                if 3.0 <= y <= 5.0: return 95.0
                if 2.0 <= y < 3.0: return 80.0
                if 5.0 < y <= 7.0: return 75.0
                if 1.0 <= y < 2.0: return 55.0
                if y > 7.0: return 50.0
                return 15.0

            def sp(p):
                if p == 0: return 30.0
                if 30 <= p <= 60: return 95.0
                if 20 <= p < 30: return 80.0
                if 60 < p <= 75: return 65.0
                if 75 < p <= 90: return 40.0
                return 20.0

            def ss(c):
                if c < 10: return 90.0
                if c < 20: return 75.0
                if c < 35: return 55.0
                return 30.0

            def sd(d):
                if d is None or d == 0: return 80.0
                if d < 50: return 90.0
                if d < 100: return 70.0
                if d < 200: return 50.0
                return 25.0

            return round(min(100, max(0,
                sy(div_yield) * 0.40 + sp(payout_ratio) * 0.25 +
                ss(change_1y) * 0.20 + sd(debt_to_equity) * 0.15
            )), 2)

    except Exception as e:
        logger.warning(f"_score_from_data({strategy}): {e}")
    return 0.0


def _build_signals(
    strategy: str, fundamentals: dict, price_data: dict, score: float
) -> list[str]:
    """Build a list of human-readable signal strings for a ticker."""
    signals = []

    if strategy == "momentum":
        m1 = price_data.get("price_change_1m_pct", 0) or 0
        m3 = price_data.get("price_change_3m_pct", 0) or 0
        rsi = price_data.get("rsi_14", 50) or 50
        ma50 = price_data.get("ma_50")
        ma200 = price_data.get("ma_200")
        current = price_data.get("current_price", 0)

        if m1 > 0:
            signals.append(f"+{m1:.1f}% price gain past month")
        if m3 > 0:
            signals.append(f"+{m3:.1f}% price gain past 3 months")
        if rsi and 50 < rsi < 70:
            signals.append(f"RSI {rsi:.0f} — bullish momentum")
        if ma50 and ma200 and current and current > ma50 > ma200:
            signals.append("Trading above 50-day and 200-day moving averages")

    elif strategy == "value":
        pe = fundamentals.get("pe_ratio")
        pb = fundamentals.get("pb_ratio")
        ev_ebitda = fundamentals.get("ev_ebitda")
        fcf = fundamentals.get("fcf_yield")

        if pe and 0 < pe < 18:
            signals.append(f"P/E of {pe:.1f}x — below market average")
        if pb and pb < 2.5:
            signals.append(f"P/B of {pb:.1f}x — trading near book value")
        if ev_ebitda and ev_ebitda < 12:
            signals.append(f"EV/EBITDA of {ev_ebitda:.1f}x — attractive valuation")
        if fcf and fcf > 4:
            signals.append(f"FCF yield of {fcf:.1f}% — strong free cash generation")

    elif strategy == "growth":
        rev_growth = fundamentals.get("revenue_growth_yoy")
        gross_margin = fundamentals.get("gross_margin")
        op_margin = fundamentals.get("operating_margin")

        if rev_growth and rev_growth > 10:
            signals.append(f"Revenue growing {rev_growth:.0f}% YoY")
        if gross_margin and gross_margin > 40:
            signals.append(f"Gross margin of {gross_margin:.0f}% — scalable business model")
        if op_margin and op_margin > 15:
            signals.append(f"Operating margin of {op_margin:.0f}% — operational leverage")

    elif strategy == "dividend":
        div_yield = fundamentals.get("dividend_yield")
        payout_ratio = fundamentals.get("payout_ratio")
        beta = fundamentals.get("beta")

        if div_yield and div_yield > 1.5:
            signals.append(f"Dividend yield of {div_yield:.1f}%")
        if payout_ratio and 20 <= payout_ratio <= 65:
            signals.append(f"Sustainable payout ratio of {payout_ratio:.0f}%")
        if beta and beta < 0.9:
            signals.append(f"Low beta of {beta:.2f} — defensive characteristics")

    signals.append(f"Strategy score: {score:.0f}/100")
    return signals
