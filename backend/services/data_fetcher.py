"""
Data fetching service for AlphaLens.

All functions are synchronous — call them via asyncio.to_thread() from async code.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sector peer universe (S&P 500 major tickers per sector)
# ---------------------------------------------------------------------------

SECTOR_PEERS: dict[str, list[str]] = {
    "Technology": [
        "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ORCL", "ADBE",
        "CSCO", "INTC", "AMD", "QCOM", "TXN", "IBM", "CRM",
    ],
    "Healthcare": [
        "UNH", "JNJ", "LLY", "ABBV", "MRK", "TMO", "ABT", "DHR",
        "PFE", "BMY", "AMGN", "GILD", "CVS", "MDT", "SYK",
    ],
    "Financials": [
        "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS",
        "BLK", "C", "AXP", "USB", "PNC", "TFC", "COF",
    ],
    "Consumer Discretionary": [
        "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "TJX", "LOW",
        "BKNG", "CMG", "GM", "F", "ROST", "EBAY", "MAR",
    ],
    "Consumer Staples": [
        "PG", "KO", "PEP", "COST", "WMT", "PM", "MO", "CL",
        "MDLZ", "EL", "KHC", "GIS", "SYY", "K", "HSY",
    ],
    "Energy": [
        "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO",
        "PXD", "OXY", "KMI", "WMB", "HES", "DVN", "FANG",
    ],
    "Industrials": [
        "UPS", "HON", "UNP", "CAT", "BA", "GE", "DE", "MMM",
        "LMT", "RTX", "EMR", "ETN", "ITW", "PH", "FDX",
    ],
    "Materials": [
        "LIN", "APD", "ECL", "SHW", "FCX", "NEM", "NUE", "VMC",
        "MLM", "DOW", "DD", "PPG", "CE", "ALB", "MOS",
    ],
    "Real Estate": [
        "PLD", "AMT", "EQIX", "PSA", "O", "WELL", "DLR", "SPG",
        "EXR", "AVB", "EQR", "VTR", "WY", "ARE", "BXP",
    ],
    "Utilities": [
        "NEE", "DUK", "SO", "D", "SRE", "AEP", "XEL", "PCG",
        "EXC", "WEC", "ED", "ETR", "FE", "ES", "PPL",
    ],
    "Communication Services": [
        "GOOGL", "META", "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS",
        "CHTR", "ATVI", "EA", "TTWO", "WBD", "PARA", "OMC",
    ],
}


# ---------------------------------------------------------------------------
# RSI helper
# ---------------------------------------------------------------------------

def _compute_rsi(series: pd.Series, period: int = 14) -> float:
    """Compute RSI for the most recent bar."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0


# ---------------------------------------------------------------------------
# Core data functions
# ---------------------------------------------------------------------------

def get_price_history(ticker: str, period: str = "1y") -> dict:
    """
    Returns price history with technical indicators.

    Keys: ticker, period, data, current_price, price_change_1d_pct,
          price_change_1m_pct, price_change_3m_pct, price_change_6m_pct,
          price_change_1y_pct, ma_50, ma_200, rsi_14
    """
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period=period)

        if hist.empty:
            raise ValueError(f"No price data for {ticker}")

        close = hist["Close"]
        current_price = float(close.iloc[-1])

        def pct_change(days: int) -> float:
            if len(close) < days + 1:
                return 0.0
            past = float(close.iloc[-(days + 1)])
            return ((current_price - past) / past) * 100 if past else 0.0

        # Trading-day approximations
        change_1d = pct_change(1)
        change_1m = pct_change(21)
        change_3m = pct_change(63)
        change_6m = pct_change(126)
        change_1y = pct_change(252) if len(close) >= 253 else pct_change(len(close) - 1)

        ma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        ma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        rsi_14 = _compute_rsi(close)

        data_records = []
        for idx, row in hist.iterrows():
            data_records.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            })

        return {
            "ticker": ticker,
            "period": period,
            "data": data_records,
            "current_price": round(current_price, 4),
            "price_change_1d_pct": round(change_1d, 2),
            "price_change_1m_pct": round(change_1m, 2),
            "price_change_3m_pct": round(change_3m, 2),
            "price_change_6m_pct": round(change_6m, 2),
            "price_change_1y_pct": round(change_1y, 2),
            "ma_50": round(ma_50, 4) if ma_50 else None,
            "ma_200": round(ma_200, 4) if ma_200 else None,
            "rsi_14": round(rsi_14, 2),
        }

    except Exception as e:
        logger.error(f"get_price_history({ticker}): {e}")
        raise


def get_fundamentals(ticker: str) -> dict:
    """
    Returns key fundamental metrics from yfinance.
    """
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}

        def safe(key, default=None):
            val = info.get(key, default)
            if val is not None and not isinstance(val, (str, bool)):
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return val
            return val

        # Revenue growth YoY from income statement
        revenue_growth_yoy = None
        try:
            fin = tk.financials
            if fin is not None and not fin.empty and "Total Revenue" in fin.index:
                rev = fin.loc["Total Revenue"]
                if len(rev) >= 2:
                    rev_current = float(rev.iloc[0])
                    rev_prior = float(rev.iloc[1])
                    if rev_prior and rev_prior != 0:
                        revenue_growth_yoy = round((rev_current - rev_prior) / abs(rev_prior) * 100, 2)
        except Exception:
            pass

        # FCF yield
        fcf_yield = None
        try:
            cashflow = tk.cashflow
            market_cap = safe("marketCap")
            if cashflow is not None and not cashflow.empty and market_cap:
                ops = cashflow.loc["Total Cash From Operating Activities"].iloc[0] if "Total Cash From Operating Activities" in cashflow.index else None
                capex = cashflow.loc["Capital Expenditures"].iloc[0] if "Capital Expenditures" in cashflow.index else 0
                if ops is not None:
                    fcf = float(ops) + float(capex)  # capex is negative in yf
                    fcf_yield = round((fcf / float(market_cap)) * 100, 2)
        except Exception:
            pass

        return {
            "ticker": ticker,
            "company_name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": safe("marketCap"),
            "pe_ratio": safe("trailingPE"),
            "forward_pe": safe("forwardPE"),
            "pb_ratio": safe("priceToBook"),
            "ps_ratio": safe("priceToSalesTrailing12Months"),
            "ev_ebitda": safe("enterpriseToEbitda"),
            "dividend_yield": round(float(info.get("dividendYield") or 0) * 100, 2),
            "payout_ratio": round(float(info.get("payoutRatio") or 0) * 100, 2),
            "beta": safe("beta"),
            "eps": safe("trailingEps"),
            "revenue_ttm": safe("totalRevenue"),
            "revenue_growth_yoy": revenue_growth_yoy,
            "gross_margin": round(float(info.get("grossMargins") or 0) * 100, 2),
            "operating_margin": round(float(info.get("operatingMargins") or 0) * 100, 2),
            "net_margin": round(float(info.get("profitMargins") or 0) * 100, 2),
            "debt_to_equity": safe("debtToEquity"),
            "current_ratio": safe("currentRatio"),
            "fcf_yield": fcf_yield,
            "as_of_date": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"get_fundamentals({ticker}): {e}")
        raise


def get_sector_peers(sector: str) -> list[str]:
    """Return list of S&P 500 tickers for the given sector."""
    # Normalize sector name with case-insensitive match
    for key, tickers in SECTOR_PEERS.items():
        if key.lower() == sector.lower():
            return tickers

    # Partial match fallback
    for key, tickers in SECTOR_PEERS.items():
        if sector.lower() in key.lower() or key.lower() in sector.lower():
            return tickers

    # Default to Technology if unknown
    logger.warning(f"Unknown sector '{sector}', defaulting to Technology peers")
    return SECTOR_PEERS["Technology"]


def get_peer_comps(ticker: str, sector: str, max_peers: int = 5) -> list[dict]:
    """
    Fetch key valuation multiples and operating metrics for sector peers.
    Excludes the target ticker. Returns list of dicts sorted by market cap desc.
    """
    peers = get_sector_peers(sector)
    peer_tickers = [t for t in peers if t.upper() != ticker.upper()][:max_peers]

    results = []
    for t in peer_tickers:
        try:
            f = get_fundamentals(t)
            results.append({
                "ticker": t,
                "company_name": f.get("company_name") or t,
                "market_cap": f.get("market_cap"),
                "pe_ratio": f.get("pe_ratio"),
                "ev_ebitda": f.get("ev_ebitda"),
                "ps_ratio": f.get("ps_ratio"),
                "pb_ratio": f.get("pb_ratio"),
                "gross_margin": f.get("gross_margin"),
                "operating_margin": f.get("operating_margin"),
                "net_margin": f.get("net_margin"),
                "revenue_growth_yoy": f.get("revenue_growth_yoy"),
                "dividend_yield": f.get("dividend_yield"),
            })
        except Exception as e:
            logger.warning(f"get_peer_comps: skipping {t}: {e}")

    # Sort by market cap descending (largest peers first)
    results.sort(key=lambda x: x.get("market_cap") or 0, reverse=True)
    return results


def get_alpha_vantage_overview(ticker: str, av_key: str) -> dict:
    """
    Fetch company overview from Alpha Vantage.
    Returns raw JSON dict. Caller should handle caching.
    """
    if not av_key:
        return {}

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "OVERVIEW",
        "symbol": ticker,
        "apikey": av_key,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # AV returns {"Information": "..."} on rate limit
        if "Information" in data or "Note" in data:
            logger.warning(f"Alpha Vantage rate limit hit for {ticker}")
            return {}
        return data
    except Exception as e:
        logger.error(f"get_alpha_vantage_overview({ticker}): {e}")
        return {}


def get_news_sentiment(ticker: str) -> dict:
    """
    Returns sentiment and recent headlines from yfinance news.
    Sentiment score is a simple heuristic based on keyword presence.
    """
    try:
        tk = yf.Ticker(ticker)
        news = tk.news or []

        positive_keywords = {
            "beat", "record", "growth", "profit", "gain", "rise", "surge",
            "strong", "exceed", "upgrade", "buy", "bullish", "up", "high",
        }
        negative_keywords = {
            "miss", "loss", "decline", "fall", "drop", "weak", "cut", "lower",
            "downgrade", "sell", "bearish", "down", "concern", "risk", "warn",
        }

        headlines = []
        sentiment_scores = []

        for article in news[:10]:
            title = article.get("title", "")
            source = article.get("publisher", "")
            link = article.get("link", "")
            timestamp = article.get("providerPublishTime", 0)

            date_str = (
                datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
                if timestamp
                else ""
            )

            headlines.append({
                "title": title,
                "source": source,
                "date": date_str,
                "url": link,
            })

            # Simple bag-of-words sentiment
            title_lower = title.lower()
            pos = sum(1 for w in positive_keywords if w in title_lower)
            neg = sum(1 for w in negative_keywords if w in title_lower)
            if pos + neg > 0:
                sentiment_scores.append((pos - neg) / (pos + neg))

        avg_sentiment = float(np.mean(sentiment_scores)) if sentiment_scores else 0.0

        return {
            "ticker": ticker,
            "sentiment_score": round(avg_sentiment, 3),
            "headlines": headlines,
        }

    except Exception as e:
        logger.error(f"get_news_sentiment({ticker}): {e}")
        return {"ticker": ticker, "sentiment_score": 0.0, "headlines": []}


# ---------------------------------------------------------------------------
# Strategy scoring functions
# ---------------------------------------------------------------------------

def compute_momentum_score(ticker: str) -> float:
    """
    Momentum score 0-100 based on:
    - 1-month price change (30%)
    - 3-month price change (30%)
    - 6-month price change (20%)
    - RSI positioning (20%)
    """
    try:
        ph = get_price_history(ticker, period="1y")

        m1 = ph.get("price_change_1m_pct", 0) or 0
        m3 = ph.get("price_change_3m_pct", 0) or 0
        m6 = ph.get("price_change_6m_pct", 0) or 0
        rsi = ph.get("rsi_14", 50) or 50

        # Normalize returns to 0-100 score (cap at ±50%)
        def norm_return(r: float) -> float:
            clamped = max(-50, min(50, r))
            return (clamped + 50) / 100 * 100

        mom_score = (
            norm_return(m1) * 0.30
            + norm_return(m3) * 0.30
            + norm_return(m6) * 0.20
        )

        # RSI score: ideal range 55-70 for momentum
        if 55 <= rsi <= 70:
            rsi_score = 90.0
        elif 45 <= rsi < 55:
            rsi_score = 60.0
        elif 70 < rsi <= 80:
            rsi_score = 70.0
        elif rsi > 80:
            rsi_score = 40.0  # overbought risk
        else:
            rsi_score = 30.0  # oversold

        score = mom_score + rsi_score * 0.20
        return round(min(100, max(0, score)), 2)

    except Exception as e:
        logger.warning(f"compute_momentum_score({ticker}): {e}")
        return 0.0


def compute_value_score(ticker: str, sector: str = "") -> float:
    """
    Value score 0-100 based on:
    - P/E ratio vs sector norms (25%)
    - P/B ratio (20%)
    - EV/EBITDA (20%)
    - FCF yield (20%)
    - P/S ratio (15%)
    """
    try:
        fund = get_fundamentals(ticker)

        pe = fund.get("pe_ratio")
        pb = fund.get("pb_ratio")
        ev_ebitda = fund.get("ev_ebitda")
        fcf_yield = fund.get("fcf_yield") or 0
        ps = fund.get("ps_ratio")

        # Score each metric (lower multiple = higher value score)
        def score_pe(pe_val):
            if pe_val is None or pe_val <= 0:
                return 50.0
            if pe_val < 12:
                return 95.0
            elif pe_val < 18:
                return 80.0
            elif pe_val < 25:
                return 60.0
            elif pe_val < 35:
                return 40.0
            else:
                return 20.0

        def score_pb(pb_val):
            if pb_val is None or pb_val <= 0:
                return 50.0
            if pb_val < 1.0:
                return 95.0
            elif pb_val < 2.0:
                return 80.0
            elif pb_val < 3.5:
                return 60.0
            elif pb_val < 5.0:
                return 40.0
            else:
                return 20.0

        def score_ev_ebitda(ev_val):
            if ev_val is None or ev_val <= 0:
                return 50.0
            if ev_val < 8:
                return 95.0
            elif ev_val < 12:
                return 75.0
            elif ev_val < 18:
                return 55.0
            elif ev_val < 25:
                return 35.0
            else:
                return 15.0

        def score_fcf(fcf_val):
            if fcf_val is None:
                return 50.0
            if fcf_val > 8:
                return 95.0
            elif fcf_val > 5:
                return 80.0
            elif fcf_val > 3:
                return 60.0
            elif fcf_val > 0:
                return 40.0
            else:
                return 20.0

        def score_ps(ps_val):
            if ps_val is None or ps_val <= 0:
                return 50.0
            if ps_val < 1.0:
                return 95.0
            elif ps_val < 2.5:
                return 75.0
            elif ps_val < 5.0:
                return 55.0
            elif ps_val < 10.0:
                return 35.0
            else:
                return 15.0

        score = (
            score_pe(pe) * 0.25
            + score_pb(pb) * 0.20
            + score_ev_ebitda(ev_ebitda) * 0.20
            + score_fcf(fcf_yield) * 0.20
            + score_ps(ps) * 0.15
        )

        return round(min(100, max(0, score)), 2)

    except Exception as e:
        logger.warning(f"compute_value_score({ticker}): {e}")
        return 0.0


def compute_growth_score(ticker: str) -> float:
    """
    Growth score 0-100 based on:
    - Revenue growth YoY (35%)
    - Gross margin (25%)
    - Operating margin (20%)
    - Revenue momentum (20%)
    """
    try:
        fund = get_fundamentals(ticker)
        ph = get_price_history(ticker, period="6mo")

        rev_growth = fund.get("revenue_growth_yoy") or 0
        gross_margin = fund.get("gross_margin") or 0
        op_margin = fund.get("operating_margin") or 0
        price_momentum_3m = ph.get("price_change_3m_pct", 0) or 0

        def score_rev_growth(g):
            if g > 40:
                return 95.0
            elif g > 25:
                return 85.0
            elif g > 15:
                return 70.0
            elif g > 8:
                return 55.0
            elif g > 0:
                return 40.0
            else:
                return 20.0

        def score_margin(m, thresholds):
            for thresh, sc in thresholds:
                if m >= thresh:
                    return sc
            return 20.0

        gross_thresholds = [(70, 95), (50, 80), (35, 65), (20, 45), (0, 30)]
        op_thresholds = [(30, 95), (20, 80), (12, 65), (5, 45), (0, 30)]

        score = (
            score_rev_growth(rev_growth) * 0.35
            + score_margin(gross_margin, gross_thresholds) * 0.25
            + score_margin(op_margin, op_thresholds) * 0.20
            + max(0, min(100, (price_momentum_3m + 30) / 60 * 100)) * 0.20
        )

        return round(min(100, max(0, score)), 2)

    except Exception as e:
        logger.warning(f"compute_growth_score({ticker}): {e}")
        return 0.0


def compute_dividend_score(ticker: str) -> float:
    """
    Dividend score 0-100 based on:
    - Dividend yield (40%)
    - Payout ratio sustainability (25%)
    - Price stability / low volatility (20%)
    - Debt-to-equity (15%)
    """
    try:
        fund = get_fundamentals(ticker)
        ph = get_price_history(ticker, period="1y")

        div_yield = fund.get("dividend_yield") or 0
        payout_ratio = fund.get("payout_ratio") or 0
        debt_to_equity = fund.get("debt_to_equity") or 0
        price_change_1y = abs(ph.get("price_change_1y_pct", 0) or 0)

        # Score yield: sweet spot is 2-6%
        def score_yield(y):
            if 3.0 <= y <= 5.0:
                return 95.0
            elif 2.0 <= y < 3.0:
                return 80.0
            elif 5.0 < y <= 7.0:
                return 75.0
            elif 1.0 <= y < 2.0:
                return 55.0
            elif y > 7.0:
                return 50.0  # risk of unsustainable
            else:
                return 15.0  # no dividend

        # Score payout: 30-60% is healthy
        def score_payout(p):
            if p == 0:
                return 30.0  # no dividend
            elif 30 <= p <= 60:
                return 95.0
            elif 20 <= p < 30:
                return 80.0
            elif 60 < p <= 75:
                return 65.0
            elif 75 < p <= 90:
                return 40.0
            else:
                return 20.0  # >90% unsustainable

        # Score stability: lower 1y abs movement = more stable
        def score_stability(change):
            if change < 10:
                return 90.0
            elif change < 20:
                return 75.0
            elif change < 35:
                return 55.0
            else:
                return 30.0

        def score_debt(dte):
            if dte is None or dte == 0:
                return 80.0
            elif dte < 50:
                return 90.0
            elif dte < 100:
                return 70.0
            elif dte < 200:
                return 50.0
            else:
                return 25.0

        score = (
            score_yield(div_yield) * 0.40
            + score_payout(payout_ratio) * 0.25
            + score_stability(price_change_1y) * 0.20
            + score_debt(debt_to_equity) * 0.15
        )

        return round(min(100, max(0, score)), 2)

    except Exception as e:
        logger.warning(f"compute_dividend_score({ticker}): {e}")
        return 0.0
