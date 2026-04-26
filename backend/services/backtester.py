"""
Strategy backtester for AlphaLens.
Uses price-based signals only (no look-ahead bias) with weekly rebalancing.
All functions are synchronous — call from async code via asyncio.to_thread().

NOTE: For all strategies (momentum, value, growth, dividend), we use a composite
of 1m and 3m price returns as the ranking signal. Full fundamental point-in-time
ranking would require historical financial statement data (e.g. Compustat), which
is not available in the MVP. Price momentum serves as a reasonable proxy and is
naturally point-in-time.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sector ETF benchmarks
# ---------------------------------------------------------------------------

SECTOR_ETFS: dict[str, str] = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}

# Sector tickers mirror data_fetcher.SECTOR_PEERS so the backtest uses the
# same universe the research agent screens.
SECTOR_TICKERS: dict[str, list[str]] = {
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
        "ED", "WEC", "ES", "DTE", "ETR", "PPL", "AES",
    ],
    "Communication Services": [
        "GOOGL", "META", "NFLX", "DIS", "CMCSA", "T", "VZ",
        "TMUS", "CHTR", "ATVI", "EA", "TTWO", "FOXA", "PARA", "WBD",
    ],
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_close(prices_df: pd.DataFrame, ticker: str) -> Optional[pd.Series]:
    """
    Safely extract a single ticker's close series from a yf.download() result.

    yfinance >= 0.2 returns a MultiIndex (field, ticker) when multiple tickers
    are requested, but a flat Index (field) when only one ticker is requested.
    We normalise both layouts here.
    """
    try:
        if isinstance(prices_df.columns, pd.MultiIndex):
            # MultiIndex: (field, ticker) — e.g. ("Close", "AAPL")
            if ticker in prices_df.columns.get_level_values(1):
                series = prices_df.xs(ticker, axis=1, level=1)
                # xs may return a DataFrame if there are multiple fields; pick Close
                if isinstance(series, pd.DataFrame):
                    series = series["Close"] if "Close" in series.columns else series.iloc[:, 0]
                return series.dropna()
        else:
            # Flat index: just ticker names (single-ticker download or already Close-extracted)
            if ticker in prices_df.columns:
                return prices_df[ticker].dropna()
    except Exception as exc:
        logger.debug("Could not extract %s from price DataFrame: %s", ticker, exc)
    return None


def _momentum_score_at(close_series: pd.Series, as_of_idx: int) -> float:
    """
    Compute a price momentum score for a ticker using data up to *as_of_idx*.
    No look-ahead: only rows 0..as_of_idx (inclusive) are used.

    Score = 0.5 * 1m_return + 0.5 * 3m_return
    Returns NaN if insufficient history.
    """
    hist = close_series.iloc[: as_of_idx + 1]
    if len(hist) < 2:
        return float("nan")

    current = hist.iloc[-1]

    # 1-month return (≈21 trading days)
    lookback_1m = max(0, len(hist) - 21)
    base_1m = hist.iloc[lookback_1m]
    ret_1m = (current / base_1m - 1) if base_1m > 0 else float("nan")

    # 3-month return (≈63 trading days)
    lookback_3m = max(0, len(hist) - 63)
    base_3m = hist.iloc[lookback_3m]
    ret_3m = (current / base_3m - 1) if base_3m > 0 else float("nan")

    if pd.isna(ret_1m) or pd.isna(ret_3m):
        return float("nan")

    return 0.5 * ret_1m + 0.5 * ret_3m


def _compute_metrics(
    portfolio_values: pd.Series,
    spy_values: pd.Series,
) -> dict:
    """Compute performance metrics from indexed value series (both start at 100)."""
    n_days = len(portfolio_values)
    if n_days < 2:
        return {}

    port_final = portfolio_values.iloc[-1]
    spy_final = spy_values.iloc[-1]

    cumulative_return = (port_final / 100.0 - 1) * 100
    spy_cumulative = (spy_final / 100.0 - 1) * 100

    # Annualised return
    years = n_days / 252.0
    annualised = ((port_final / 100.0) ** (1.0 / years) - 1) * 100 if years > 0 else 0.0

    # Daily returns
    daily_rets = portfolio_values.pct_change().dropna()
    volatility = float(daily_rets.std() * (252 ** 0.5) * 100)

    # Sharpe (risk-free = 0)
    sharpe = annualised / volatility if volatility > 0 else 0.0

    # Max drawdown
    running_max = portfolio_values.cummax()
    drawdowns = (portfolio_values / running_max - 1)
    max_drawdown = float(drawdowns.min() * 100)  # negative number

    # Win rate: % of weekly periods where portfolio beat SPY
    port_weekly = portfolio_values.iloc[::5].pct_change().dropna()
    spy_weekly = spy_values.iloc[::5].pct_change().dropna()
    aligned_port, aligned_spy = port_weekly.align(spy_weekly, join="inner")
    win_rate = float((aligned_port > aligned_spy).mean() * 100) if len(aligned_port) > 0 else 0.0

    alpha = cumulative_return - spy_cumulative

    return {
        "cumulative_return_pct": round(cumulative_return, 2),
        "annualized_return_pct": round(annualised, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown_pct": round(max_drawdown, 2),
        "win_rate_pct": round(win_rate, 1),
        "alpha_vs_spy_pct": round(alpha, 2),
        "volatility_pct": round(volatility, 2),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_backtest(strategy: str, sector: str, period: str = "1y") -> dict:
    """
    Run a historical backtest for the given strategy + sector.

    All strategies use price-based 1m/3m momentum signals (point-in-time safe).
    Fundamental signals (value, growth, dividend) would require historical
    financials data that is not available in this MVP.

    Args:
        strategy: "momentum" | "value" | "growth" | "dividend"
        sector:   One of the keys in SECTOR_TICKERS
        period:   "1y" | "2y"

    Returns:
        {
            strategy, sector, period,
            metrics: {cumulative_return_pct, annualized_return_pct, sharpe_ratio,
                      max_drawdown_pct, win_rate_pct, alpha_vs_spy_pct, volatility_pct},
            chart_data: [{date, portfolio, spy, sector_etf}, ...]
        }
    """
    logger.info("Starting backtest: strategy=%s sector=%s period=%s", strategy, sector, period)

    # ------------------------------------------------------------------
    # 1. Validate inputs
    # ------------------------------------------------------------------
    sector_tickers = SECTOR_TICKERS.get(sector)
    if not sector_tickers:
        raise ValueError(f"Unknown sector: {sector!r}. Valid sectors: {list(SECTOR_TICKERS)}")

    sector_etf = SECTOR_ETFS.get(sector, "SPY")

    # ------------------------------------------------------------------
    # 2. Download all price data in one batch call
    # ------------------------------------------------------------------
    all_tickers = list(sector_tickers) + ["SPY", sector_etf]
    # Deduplicate while preserving order (sector_etf might equal SPY for some sectors)
    seen: set[str] = set()
    unique_tickers: list[str] = []
    for t in all_tickers:
        if t not in seen:
            unique_tickers.append(t)
            seen.add(t)

    logger.info("Downloading price data for %d tickers: %s", len(unique_tickers), unique_tickers)

    try:
        raw = yf.download(
            tickers=unique_tickers,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as exc:
        logger.error("yfinance download failed: %s", exc)
        raise RuntimeError(f"Failed to download price data: {exc}") from exc

    # Extract the Close level if we got a MultiIndex back
    if isinstance(raw.columns, pd.MultiIndex):
        try:
            prices = raw["Close"]
        except KeyError:
            # Some yfinance versions capitalise differently
            prices = raw.xs("Close", axis=1, level=0) if "Close" in raw.columns.get_level_values(0) else raw
    else:
        prices = raw

    logger.info("Downloaded price DataFrame shape: %s", prices.shape)

    if prices.empty:
        raise RuntimeError("Downloaded price data is empty — yfinance may be rate-limited.")

    # ------------------------------------------------------------------
    # 3. Build clean close series per ticker
    # ------------------------------------------------------------------
    ticker_series: dict[str, pd.Series] = {}
    for t in unique_tickers:
        series = _extract_close(prices, t)
        if series is None or len(series) < 30:
            logger.warning("Skipping %s — insufficient price history (got %s rows)",
                           t, 0 if series is None else len(series))
            continue
        ticker_series[t] = series

    valid_sector_tickers = [t for t in sector_tickers if t in ticker_series]
    logger.info("%d / %d sector tickers have valid price data", len(valid_sector_tickers), len(sector_tickers))

    if len(valid_sector_tickers) < 1:
        raise RuntimeError("No valid sector ticker data available for backtesting.")

    if "SPY" not in ticker_series:
        raise RuntimeError("Could not download SPY data — benchmark unavailable.")

    # ------------------------------------------------------------------
    # 4. Align all series to a common date index (SPY as reference)
    # ------------------------------------------------------------------
    # Use the SPY index as the master calendar
    spy_series = ticker_series["SPY"]
    common_index = spy_series.index

    # Reindex all sector tickers to common index, forward-fill gaps (e.g. holidays)
    aligned: dict[str, pd.Series] = {}
    for t in valid_sector_tickers:
        aligned[t] = ticker_series[t].reindex(common_index).ffill()

    spy_aligned = spy_series.reindex(common_index).ffill()

    # Sector ETF — fall back to SPY if not available
    if sector_etf in ticker_series:
        etf_aligned = ticker_series[sector_etf].reindex(common_index).ffill()
    else:
        logger.warning("Sector ETF %s not available, falling back to SPY", sector_etf)
        etf_aligned = spy_aligned.copy()

    n_days = len(common_index)
    logger.info("Backtest calendar: %d trading days (%s → %s)",
                n_days, common_index[0].date(), common_index[-1].date())

    # ------------------------------------------------------------------
    # 5. Simulate portfolio with weekly rebalancing
    # ------------------------------------------------------------------
    # Rebalance on day 0 and every 5 trading days thereafter
    rebalance_indices = list(range(0, n_days, 5))

    portfolio_values = np.ones(n_days) * 100.0   # starts at 100
    spy_values = np.ones(n_days) * 100.0
    etf_values = np.ones(n_days) * 100.0

    current_holdings: list[str] = []  # equal-weight top 3

    # Initialise benchmark values at start price
    spy_start = spy_aligned.iloc[0]
    etf_start = etf_aligned.iloc[0] if etf_aligned.iloc[0] > 0 else spy_start

    logger.info("Running simulation with %d rebalance points", len(rebalance_indices))

    for i, rb_idx in enumerate(rebalance_indices):
        # Score each sector ticker using data up to this date (point-in-time)
        scores: dict[str, float] = {}
        for t in valid_sector_tickers:
            s = aligned[t]
            # Need at least 5 non-NaN rows before this point to score
            hist_to_here = s.iloc[: rb_idx + 1].dropna()
            if len(hist_to_here) < 5:
                continue
            # Compute score index within the full series
            score_idx = len(s.iloc[: rb_idx + 1]) - 1
            sc = _momentum_score_at(s, score_idx)
            if not pd.isna(sc):
                scores[t] = sc

        if scores:
            top3 = sorted(scores, key=lambda t: scores[t], reverse=True)[:3]
            current_holdings = top3
            logger.debug("Rebalance day %d (%s): top picks = %s",
                         rb_idx, common_index[rb_idx].date(), current_holdings)
        else:
            logger.warning("No valid scores on rebalance day %d — keeping previous holdings", rb_idx)

        # Determine the date range for this holding period
        next_rb_idx = rebalance_indices[i + 1] if i + 1 < len(rebalance_indices) else n_days

        if not current_holdings:
            # No holdings — keep flat (portfolio stays at previous value)
            prev_val = portfolio_values[rb_idx - 1] if rb_idx > 0 else 100.0
            portfolio_values[rb_idx:next_rb_idx] = prev_val
        else:
            # Equal-weight return over the holding period
            prev_port_val = portfolio_values[rb_idx - 1] if rb_idx > 0 else 100.0

            for day in range(rb_idx, next_rb_idx):
                if day == 0:
                    portfolio_values[day] = 100.0
                    continue

                daily_port_ret = 0.0
                valid_count = 0
                for t in current_holdings:
                    prev_p = aligned[t].iloc[day - 1]
                    curr_p = aligned[t].iloc[day]
                    if prev_p > 0 and not pd.isna(prev_p) and not pd.isna(curr_p):
                        daily_port_ret += (curr_p / prev_p - 1)
                        valid_count += 1

                if valid_count > 0:
                    daily_port_ret /= valid_count  # equal weight average
                    portfolio_values[day] = portfolio_values[day - 1] * (1 + daily_port_ret)
                else:
                    portfolio_values[day] = portfolio_values[day - 1]

        # Compute SPY and ETF values for the same period (day-by-day)
        for day in range(rb_idx, next_rb_idx):
            if day == 0:
                spy_values[day] = 100.0
                etf_values[day] = 100.0
                continue
            prev_spy = spy_aligned.iloc[day - 1]
            curr_spy = spy_aligned.iloc[day]
            if prev_spy > 0 and not pd.isna(prev_spy) and not pd.isna(curr_spy):
                spy_values[day] = spy_values[day - 1] * (curr_spy / prev_spy)
            else:
                spy_values[day] = spy_values[day - 1]

            prev_etf = etf_aligned.iloc[day - 1]
            curr_etf = etf_aligned.iloc[day]
            if prev_etf > 0 and not pd.isna(prev_etf) and not pd.isna(curr_etf):
                etf_values[day] = etf_values[day - 1] * (curr_etf / prev_etf)
            else:
                etf_values[day] = etf_values[day - 1]

    # ------------------------------------------------------------------
    # 6. Compute metrics
    # ------------------------------------------------------------------
    port_series = pd.Series(portfolio_values, index=common_index)
    spy_series_indexed = pd.Series(spy_values, index=common_index)

    metrics = _compute_metrics(port_series, spy_series_indexed)
    logger.info("Backtest complete. Metrics: %s", metrics)

    # ------------------------------------------------------------------
    # 7. Build chart data (sample every 5 days to keep payload small)
    # ------------------------------------------------------------------
    sample_indices = list(range(0, n_days, 5))
    if n_days - 1 not in sample_indices:
        sample_indices.append(n_days - 1)  # always include last point

    chart_data = []
    for idx in sample_indices:
        chart_data.append({
            "date": common_index[idx].strftime("%Y-%m-%d"),
            "portfolio": round(float(portfolio_values[idx]), 2),
            "spy": round(float(spy_values[idx]), 2),
            "sector_etf": round(float(etf_values[idx]), 2),
        })

    return {
        "strategy": strategy,
        "sector": sector,
        "period": period,
        "metrics": metrics,
        "chart_data": chart_data,
    }
