"""
Data fetching service for AlphaLens.

All functions are synchronous — call them via asyncio.to_thread() from async code.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory Alpha Vantage cache (avoids burning 25 req/day on repeated calls)
# Key: ticker, Value: (data_dict, unix_timestamp_fetched)
# TTL: 23 hours so we never hit the 25/day wall within a server session
# ---------------------------------------------------------------------------
_AV_MEMORY_CACHE = {}
_AV_CACHE_TTL_SECONDS = 23 * 3600  # 23 hours


# ---------------------------------------------------------------------------
# Static fundamentals fallback (last-resort when yfinance AND AV both fail)
# Values are approximate trailing-twelve-month figures sourced from public
# financial data. Used only when live data is unavailable.
# ---------------------------------------------------------------------------
_STATIC_FUNDAMENTALS = {
    "AAPL": dict(company_name="Apple Inc.", sector="Technology", industry="Consumer Electronics",
                 market_cap=3_050_000_000_000, pe_ratio=33.0, forward_pe=28.5, pb_ratio=49.0,
                 ps_ratio=8.1, ev_ebitda=24.0, dividend_yield=0.5, payout_ratio=15.0,
                 beta=1.2, eps=7.02, revenue_ttm=398_000_000_000, revenue_growth_yoy=5.1,
                 gross_margin=46.2, operating_margin=31.0, net_margin=24.3, debt_to_equity=175.0,
                 current_ratio=0.9, fcf_yield=3.8),
    "MSFT": dict(company_name="Microsoft Corporation", sector="Technology", industry="Software—Infrastructure",
                 market_cap=3_300_000_000_000, pe_ratio=35.0, forward_pe=29.0, pb_ratio=13.0,
                 ps_ratio=13.5, ev_ebitda=27.5, dividend_yield=0.7, payout_ratio=25.0,
                 beta=0.9, eps=13.50, revenue_ttm=245_000_000_000, revenue_growth_yoy=16.0,
                 gross_margin=70.1, operating_margin=44.2, net_margin=35.0, debt_to_equity=38.0,
                 current_ratio=1.3, fcf_yield=2.8),
    "NVDA": dict(company_name="NVIDIA Corporation", sector="Technology", industry="Semiconductors",
                 market_cap=3_600_000_000_000, pe_ratio=33.5, forward_pe=22.0, pb_ratio=36.0,
                 ps_ratio=19.0, ev_ebitda=42.0, dividend_yield=0.03, payout_ratio=1.0,
                 beta=1.7, eps=2.99, revenue_ttm=130_000_000_000, revenue_growth_yoy=122.0,
                 gross_margin=65.5, operating_margin=56.0, net_margin=53.0, debt_to_equity=12.0,
                 current_ratio=4.2, fcf_yield=2.5),
    "GOOGL": dict(company_name="Alphabet Inc.", sector="Communication Services", industry="Internet Content & Information",
                  market_cap=2_200_000_000_000, pe_ratio=21.5, forward_pe=17.5, pb_ratio=7.5,
                  ps_ratio=7.2, ev_ebitda=16.5, dividend_yield=0.5, payout_ratio=8.0,
                  beta=1.1, eps=8.84, revenue_ttm=355_000_000_000, revenue_growth_yoy=14.0,
                  gross_margin=57.5, operating_margin=31.5, net_margin=24.0, debt_to_equity=5.0,
                  current_ratio=1.9, fcf_yield=4.5),
    "GOOG": dict(company_name="Alphabet Inc.", sector="Communication Services", industry="Internet Content & Information",
                 market_cap=2_200_000_000_000, pe_ratio=21.5, forward_pe=17.5, pb_ratio=7.5,
                 ps_ratio=7.2, ev_ebitda=16.5, dividend_yield=0.5, payout_ratio=8.0,
                 beta=1.1, eps=8.84, revenue_ttm=355_000_000_000, revenue_growth_yoy=14.0,
                 gross_margin=57.5, operating_margin=31.5, net_margin=24.0, debt_to_equity=5.0,
                 current_ratio=1.9, fcf_yield=4.5),
    "META": dict(company_name="Meta Platforms Inc.", sector="Communication Services", industry="Internet Content & Information",
                 market_cap=1_700_000_000_000, pe_ratio=25.0, forward_pe=20.5, pb_ratio=9.5,
                 ps_ratio=9.0, ev_ebitda=18.5, dividend_yield=0.3, payout_ratio=7.0,
                 beta=1.2, eps=23.0, revenue_ttm=165_000_000_000, revenue_growth_yoy=22.0,
                 gross_margin=81.0, operating_margin=42.0, net_margin=35.0, debt_to_equity=11.0,
                 current_ratio=2.7, fcf_yield=3.5),
    "AMZN": dict(company_name="Amazon.com Inc.", sector="Consumer Discretionary", industry="Internet Retail",
                 market_cap=2_400_000_000_000, pe_ratio=40.0, forward_pe=28.0, pb_ratio=10.0,
                 ps_ratio=4.0, ev_ebitda=22.0, dividend_yield=0.0, payout_ratio=0.0,
                 beta=1.1, eps=5.53, revenue_ttm=640_000_000_000, revenue_growth_yoy=11.0,
                 gross_margin=48.0, operating_margin=10.5, net_margin=8.0, debt_to_equity=50.0,
                 current_ratio=1.1, fcf_yield=2.5),
    "TSLA": dict(company_name="Tesla Inc.", sector="Consumer Discretionary", industry="Auto Manufacturers",
                 market_cap=920_000_000_000, pe_ratio=95.0, forward_pe=58.0, pb_ratio=12.0,
                 ps_ratio=8.5, ev_ebitda=52.0, dividend_yield=0.0, payout_ratio=0.0,
                 beta=2.3, eps=1.81, revenue_ttm=100_000_000_000, revenue_growth_yoy=1.0,
                 gross_margin=17.5, operating_margin=6.0, net_margin=5.0, debt_to_equity=8.0,
                 current_ratio=1.8, fcf_yield=0.8),
    "AVGO": dict(company_name="Broadcom Inc.", sector="Technology", industry="Semiconductors",
                 market_cap=1_100_000_000_000, pe_ratio=28.0, forward_pe=22.5, pb_ratio=14.0,
                 ps_ratio=10.5, ev_ebitda=26.0, dividend_yield=1.2, payout_ratio=30.0,
                 beta=1.1, eps=5.12, revenue_ttm=55_000_000_000, revenue_growth_yoy=44.0,
                 gross_margin=64.0, operating_margin=45.0, net_margin=28.0, debt_to_equity=100.0,
                 current_ratio=1.1, fcf_yield=4.2),
    "CRM": dict(company_name="Salesforce Inc.", sector="Technology", industry="Software—Application",
                market_cap=320_000_000_000, pe_ratio=30.0, forward_pe=25.0, pb_ratio=4.5,
                ps_ratio=7.5, ev_ebitda=22.0, dividend_yield=0.6, payout_ratio=15.0,
                beta=1.1, eps=9.85, revenue_ttm=38_000_000_000, revenue_growth_yoy=9.0,
                gross_margin=76.0, operating_margin=18.0, net_margin=14.0, debt_to_equity=25.0,
                current_ratio=1.0, fcf_yield=4.0),
    "ADBE": dict(company_name="Adobe Inc.", sector="Technology", industry="Software—Application",
                 market_cap=190_000_000_000, pe_ratio=28.0, forward_pe=22.0, pb_ratio=12.0,
                 ps_ratio=8.5, ev_ebitda=20.0, dividend_yield=0.0, payout_ratio=0.0,
                 beta=1.0, eps=18.0, revenue_ttm=22_000_000_000, revenue_growth_yoy=10.0,
                 gross_margin=88.0, operating_margin=34.0, net_margin=26.0, debt_to_equity=88.0,
                 current_ratio=1.1, fcf_yield=4.0),
    # Healthcare
    "LLY": dict(company_name="Eli Lilly and Company", sector="Healthcare", industry="Drug Manufacturers—General",
                market_cap=850_000_000_000, pe_ratio=50.0, forward_pe=32.0, pb_ratio=70.0,
                ps_ratio=20.0, ev_ebitda=42.0, dividend_yield=0.6, payout_ratio=25.0,
                beta=0.4, eps=13.5, revenue_ttm=47_000_000_000, revenue_growth_yoy=32.0,
                gross_margin=80.5, operating_margin=30.5, net_margin=26.0, debt_to_equity=185.0,
                current_ratio=1.2, fcf_yield=2.0),
    "JNJ": dict(company_name="Johnson & Johnson", sector="Healthcare", industry="Drug Manufacturers—General",
                market_cap=380_000_000_000, pe_ratio=16.0, forward_pe=14.0, pb_ratio=5.0,
                ps_ratio=5.0, ev_ebitda=14.0, dividend_yield=3.1, payout_ratio=45.0,
                beta=0.5, eps=5.79, revenue_ttm=89_000_000_000, revenue_growth_yoy=4.0,
                gross_margin=69.0, operating_margin=20.0, net_margin=14.0, debt_to_equity=55.0,
                current_ratio=1.3, fcf_yield=5.0),
    "ABBV": dict(company_name="AbbVie Inc.", sector="Healthcare", industry="Drug Manufacturers—General",
                 market_cap=325_000_000_000, pe_ratio=20.0, forward_pe=16.0, pb_ratio=12.0,
                 ps_ratio=4.5, ev_ebitda=15.0, dividend_yield=3.4, payout_ratio=65.0,
                 beta=0.7, eps=11.1, revenue_ttm=58_000_000_000, revenue_growth_yoy=4.0,
                 gross_margin=70.0, operating_margin=22.0, net_margin=17.0, debt_to_equity=405.0,
                 current_ratio=0.9, fcf_yield=5.5),
    "MRK": dict(company_name="Merck & Co. Inc.", sector="Healthcare", industry="Drug Manufacturers—General",
                market_cap=280_000_000_000, pe_ratio=15.0, forward_pe=12.0, pb_ratio=4.5,
                ps_ratio=3.5, ev_ebitda=11.0, dividend_yield=2.9, payout_ratio=40.0,
                beta=0.4, eps=7.82, revenue_ttm=63_000_000_000, revenue_growth_yoy=7.0,
                gross_margin=73.0, operating_margin=28.0, net_margin=17.0, debt_to_equity=80.0,
                current_ratio=1.3, fcf_yield=6.0),
    "TMO": dict(company_name="Thermo Fisher Scientific", sector="Healthcare", industry="Diagnostics & Research",
                market_cap=205_000_000_000, pe_ratio=28.0, forward_pe=23.0, pb_ratio=5.0,
                ps_ratio=4.5, ev_ebitda=19.0, dividend_yield=0.3, payout_ratio=8.0,
                beta=0.7, eps=22.0, revenue_ttm=43_000_000_000, revenue_growth_yoy=-2.0,
                gross_margin=42.0, operating_margin=18.0, net_margin=14.0, debt_to_equity=70.0,
                current_ratio=1.8, fcf_yield=3.5),
    # Financials
    "JPM": dict(company_name="JPMorgan Chase & Co.", sector="Financials", industry="Banks—Diversified",
                market_cap=750_000_000_000, pe_ratio=13.0, forward_pe=12.0, pb_ratio=2.2,
                ps_ratio=3.5, ev_ebitda=None, dividend_yield=2.2, payout_ratio=28.0,
                beta=1.2, eps=19.0, revenue_ttm=175_000_000_000, revenue_growth_yoy=10.0,
                gross_margin=None, operating_margin=37.0, net_margin=27.0, debt_to_equity=None,
                current_ratio=None, fcf_yield=None),
    "BAC": dict(company_name="Bank of America Corp.", sector="Financials", industry="Banks—Diversified",
                market_cap=360_000_000_000, pe_ratio=14.0, forward_pe=12.5, pb_ratio=1.5,
                ps_ratio=2.5, ev_ebitda=None, dividend_yield=2.4, payout_ratio=32.0,
                beta=1.4, eps=3.39, revenue_ttm=100_000_000_000, revenue_growth_yoy=5.0,
                gross_margin=None, operating_margin=25.0, net_margin=21.0, debt_to_equity=None,
                current_ratio=None, fcf_yield=None),
    "GS": dict(company_name="Goldman Sachs Group Inc.", sector="Financials", industry="Capital Markets",
               market_cap=210_000_000_000, pe_ratio=14.0, forward_pe=12.0, pb_ratio=1.7,
               ps_ratio=2.0, ev_ebitda=None, dividend_yield=2.2, payout_ratio=28.0,
               beta=1.5, eps=42.0, revenue_ttm=60_000_000_000, revenue_growth_yoy=16.0,
               gross_margin=None, operating_margin=30.0, net_margin=24.0, debt_to_equity=None,
               current_ratio=None, fcf_yield=None),
    "V": dict(company_name="Visa Inc.", sector="Financials", industry="Credit Services",
              market_cap=620_000_000_000, pe_ratio=30.0, forward_pe=25.5, pb_ratio=14.0,
              ps_ratio=16.0, ev_ebitda=22.0, dividend_yield=0.8, payout_ratio=22.0,
              beta=0.9, eps=10.5, revenue_ttm=37_000_000_000, revenue_growth_yoy=10.0,
              gross_margin=80.0, operating_margin=66.0, net_margin=53.0, debt_to_equity=140.0,
              current_ratio=1.5, fcf_yield=3.5),
    # Energy
    "XOM": dict(company_name="Exxon Mobil Corp.", sector="Energy", industry="Oil & Gas Integrated",
                market_cap=520_000_000_000, pe_ratio=14.0, forward_pe=12.5, pb_ratio=2.0,
                ps_ratio=1.4, ev_ebitda=8.0, dividend_yield=3.5, payout_ratio=45.0,
                beta=0.9, eps=8.38, revenue_ttm=390_000_000_000, revenue_growth_yoy=-5.0,
                gross_margin=32.0, operating_margin=13.0, net_margin=9.0, debt_to_equity=18.0,
                current_ratio=1.4, fcf_yield=7.0),
    "CVX": dict(company_name="Chevron Corporation", sector="Energy", industry="Oil & Gas Integrated",
                market_cap=285_000_000_000, pe_ratio=14.5, forward_pe=13.0, pb_ratio=1.8,
                ps_ratio=1.4, ev_ebitda=7.5, dividend_yield=4.2, payout_ratio=55.0,
                beta=0.8, eps=10.7, revenue_ttm=195_000_000_000, revenue_growth_yoy=-8.0,
                gross_margin=35.0, operating_margin=14.0, net_margin=10.0, debt_to_equity=15.0,
                current_ratio=1.3, fcf_yield=8.0),
    # Consumer Staples
    "WMT": dict(company_name="Walmart Inc.", sector="Consumer Staples", industry="Discount Stores",
                market_cap=780_000_000_000, pe_ratio=32.0, forward_pe=27.0, pb_ratio=8.5,
                ps_ratio=1.0, ev_ebitda=18.0, dividend_yield=1.0, payout_ratio=30.0,
                beta=0.5, eps=2.45, revenue_ttm=680_000_000_000, revenue_growth_yoy=5.0,
                gross_margin=24.4, operating_margin=4.5, net_margin=2.9, debt_to_equity=80.0,
                current_ratio=0.8, fcf_yield=3.0),
    "COST": dict(company_name="Costco Wholesale Corp.", sector="Consumer Staples", industry="Discount Stores",
                 market_cap=440_000_000_000, pe_ratio=55.0, forward_pe=47.0, pb_ratio=15.0,
                 ps_ratio=1.5, ev_ebitda=32.0, dividend_yield=0.6, payout_ratio=28.0,
                 beta=0.7, eps=18.0, revenue_ttm=248_000_000_000, revenue_growth_yoy=8.0,
                 gross_margin=12.5, operating_margin=4.2, net_margin=3.0, debt_to_equity=45.0,
                 current_ratio=1.0, fcf_yield=2.0),
    # Industrials
    "CAT": dict(company_name="Caterpillar Inc.", sector="Industrials", industry="Farm & Heavy Construction Machinery",
                market_cap=195_000_000_000, pe_ratio=16.0, forward_pe=14.5, pb_ratio=12.0,
                ps_ratio=2.5, ev_ebitda=13.0, dividend_yield=1.6, payout_ratio=24.0,
                beta=1.1, eps=21.0, revenue_ttm=65_000_000_000, revenue_growth_yoy=-4.0,
                gross_margin=37.0, operating_margin=19.0, net_margin=15.0, debt_to_equity=170.0,
                current_ratio=1.4, fcf_yield=6.0),
    # Real Estate / Utilities
    "NEE": dict(company_name="NextEra Energy Inc.", sector="Utilities", industry="Utilities—Regulated Electric",
                market_cap=155_000_000_000, pe_ratio=18.0, forward_pe=16.0, pb_ratio=2.9,
                ps_ratio=5.0, ev_ebitda=14.0, dividend_yield=3.0, payout_ratio=55.0,
                beta=0.6, eps=3.55, revenue_ttm=24_000_000_000, revenue_growth_yoy=7.0,
                gross_margin=42.0, operating_margin=25.0, net_margin=15.0, debt_to_equity=180.0,
                current_ratio=0.6, fcf_yield=None),
}

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

    On rate-limit or data unavailability, returns a minimal dict with
    available fields rather than raising (prevents full pipeline crash).
    """
    _empty = {
        "ticker": ticker, "period": period, "data": [],
        "current_price": None, "price_change_1d_pct": None,
        "price_change_1m_pct": None, "price_change_3m_pct": None,
        "price_change_6m_pct": None, "price_change_1y_pct": None,
        "ma_50": None, "ma_200": None, "rsi_14": None,
        "note": "Price data temporarily unavailable (rate limited)",
    }
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period=period)

        if hist.empty:
            logger.warning(f"get_price_history({ticker}): empty history returned")
            return _empty

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
        logger.warning(f"get_price_history({ticker}) failed ({type(e).__name__}): {e}")
        # Try Alpha Vantage GLOBAL_QUOTE as a minimal price fallback
        try:
            from models.database import settings as _s
            if _s.alpha_vantage_api_key:
                resp = requests.get(
                    "https://www.alphavantage.co/query",
                    params={"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": _s.alpha_vantage_api_key},
                    timeout=8,
                )
                q = resp.json().get("Global Quote", {})
                if q.get("05. price"):
                    price = float(q["05. price"])
                    chg_pct = float(q.get("10. change percent", "0").rstrip("%"))
                    return {**_empty, "current_price": round(price, 2),
                            "price_change_1d_pct": round(chg_pct, 2), "note": "Price via Alpha Vantage"}
        except Exception as av_e:
            logger.warning(f"AV price fallback also failed for {ticker}: {av_e}")
        return _empty


def get_fundamentals(ticker: str) -> dict:
    """
    Returns key fundamental metrics.
    Source priority:
    1. yfinance tk.info (fast, free, but rate-limited on cloud IPs)
    2. Alpha Vantage OVERVIEW (with in-memory cache to stay under 25 req/day)
    3. Static hardcoded fallback for major tickers (always available)
    """
    from models.database import settings as _settings
    ticker_upper = ticker.upper()
    try:
        # In FAST_MODE, skip yfinance tk.info entirely — it hangs on rate-limited cloud IPs.
        # Go straight to Alpha Vantage → static fallback.
        tk = None
        if _settings.fast_mode:
            info = {}
        else:
            try:
                tk = yf.Ticker(ticker_upper)
                info = tk.info or {}
            except Exception as yfe:
                logger.warning(f"yfinance .info error for {ticker_upper}: {yfe}")
                info = {}

        # If yfinance returns an empty/minimal dict (rate-limited), fall back to AV then static
        if not info.get("trailingPE") and not info.get("totalRevenue"):
            if _settings.alpha_vantage_api_key:
                logger.info(f"yfinance returned empty data for {ticker_upper}, trying Alpha Vantage...")
                av_data = get_alpha_vantage_overview(ticker_upper, _settings.alpha_vantage_api_key)
                if av_data:
                    return _fundamentals_from_av(ticker_upper, av_data)
            # AV also failed (or no key) — use static fallback if available
            if ticker_upper in _STATIC_FUNDAMENTALS:
                logger.info(f"Using static fundamentals fallback for {ticker_upper}")
                static = _STATIC_FUNDAMENTALS[ticker_upper].copy()
                static["ticker"] = ticker_upper
                static["as_of_date"] = datetime.utcnow().isoformat()
                static["source"] = "static_fallback"
                return static


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
            fin = tk.financials if tk is not None else None
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
            cashflow = tk.cashflow if tk is not None else None
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


def _fundamentals_from_av(ticker: str, av: dict) -> dict:
    """Map Alpha Vantage OVERVIEW response to the same shape as get_fundamentals."""
    def _f(key, pct=False):
        v = av.get(key)
        if v in (None, "None", "-", ""):
            return None
        try:
            val = float(v)
            return round(val * 100, 2) if pct else val
        except (TypeError, ValueError):
            return None

    return {
        "ticker": ticker,
        "company_name": av.get("Name"),
        "sector": av.get("Sector"),
        "industry": av.get("Industry"),
        "market_cap": _f("MarketCapitalization"),
        "pe_ratio": _f("TrailingPE"),
        "forward_pe": _f("ForwardPE"),
        "pb_ratio": _f("PriceToBookRatio"),
        "ps_ratio": _f("PriceToSalesRatioTTM"),
        "ev_ebitda": _f("EVToEBITDA"),
        "dividend_yield": _f("DividendYield", pct=True),
        "payout_ratio": None,
        "beta": _f("Beta"),
        "eps": _f("EPS"),
        "revenue_ttm": _f("RevenueTTM"),
        "revenue_growth_yoy": _f("QuarterlyRevenueGrowthYOY", pct=True),
        "gross_margin": (round(_f("GrossProfitTTM") / _f("RevenueTTM") * 100, 2)
                        if (_f("GrossProfitTTM") is not None and _f("RevenueTTM"))
                        else None),
        "operating_margin": _f("OperatingMarginTTM", pct=True),
        "net_margin": _f("ProfitMargin", pct=True),
        "debt_to_equity": _f("DebtToEquityRatio"),
        "current_ratio": None,
        "fcf_yield": None,
        "as_of_date": datetime.utcnow().isoformat(),
        "source": "alpha_vantage",
    }


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
    Fetch company overview from Alpha Vantage, with in-memory caching.
    Checks _AV_MEMORY_CACHE before hitting the API to stay under 25 req/day.
    """
    if not av_key:
        return {}

    ticker_upper = ticker.upper()

    # Check in-memory cache first
    if ticker_upper in _AV_MEMORY_CACHE:
        cached_data, cached_at = _AV_MEMORY_CACHE[ticker_upper]
        if time.time() - cached_at < _AV_CACHE_TTL_SECONDS:
            logger.info(f"Alpha Vantage cache hit for {ticker_upper}")
            return cached_data

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "OVERVIEW",
        "symbol": ticker_upper,
        "apikey": av_key,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # AV returns {"Information": "..."} on rate limit
        if "Information" in data or "Note" in data:
            logger.warning(f"Alpha Vantage rate limit hit for {ticker_upper}")
            return {}
        if data and data.get("Symbol"):
            # Cache valid response
            _AV_MEMORY_CACHE[ticker_upper] = (data, time.time())
            logger.info(f"Alpha Vantage data fetched and cached for {ticker_upper}")
        return data
    except Exception as e:
        logger.error(f"get_alpha_vantage_overview({ticker_upper}): {e}")
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
