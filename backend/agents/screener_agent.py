"""
ScreenerAgent: screens tickers by strategy and sector, returns ranked picks.
"""

import asyncio
import logging
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
                # Compute strategy score
                if strategy == "value":
                    score = score_fn(ticker, sector)
                else:
                    score = score_fn(ticker)

                if score <= 0:
                    continue

                # Gather data package (fundamentals + price history + news)
                fundamentals = get_fundamentals(ticker)
                price_data = get_price_history(ticker, period="1y")
                news = get_news_sentiment(ticker)

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

                # Build human-readable signals summary
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
                continue

        # Sort by score descending, return top N
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:num_picks]

    async def screen_async(
        self, strategy: str, sector: str, num_picks: int = 3
    ) -> list[dict[str, Any]]:
        """Async wrapper — runs synchronous screen() in a thread."""
        return await asyncio.to_thread(self.screen, strategy, sector, num_picks)


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
