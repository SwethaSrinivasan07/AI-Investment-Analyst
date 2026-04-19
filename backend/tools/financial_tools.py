"""
Financial tools that Claude can call via tool use.

Each executor function takes the tool input dict and returns a JSON-serializable string.
The FINANCIAL_TOOLS list provides the JSON schemas passed to the Anthropic API.
"""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (JSON schemas for the Anthropic API)
# ---------------------------------------------------------------------------

FINANCIAL_TOOLS: list[dict] = [
    {
        "name": "get_price_history",
        "description": (
            "Fetch price history and technical indicators for a stock ticker. "
            "Returns OHLCV data, current price, momentum metrics (1M/3M/6M/1Y returns), "
            "MA50, MA200, and RSI-14."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g. AAPL)",
                },
                "period": {
                    "type": "string",
                    "enum": ["1mo", "3mo", "6mo", "1y", "2y"],
                    "description": "Historical period to fetch",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_fundamentals",
        "description": (
            "Fetch key financial ratios and fundamentals for a stock: "
            "P/E, P/B, EV/EBITDA, margins, growth rates, debt ratios, dividend yield."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "search_sec_filings",
        "description": (
            "Search SEC filings (10-K, 10-Q, 8-K) for a ticker using semantic search. "
            "Returns relevant text chunks from real SEC documents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol",
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Natural language search query "
                        "(e.g. 'revenue growth drivers', 'competitive moat', 'risk factors')"
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 4)",
                    "default": 4,
                },
            },
            "required": ["ticker", "query"],
        },
    },
    {
        "name": "get_news_sentiment",
        "description": (
            "Get recent news headlines and aggregated sentiment score for a stock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol",
                },
                "days": {
                    "type": "integer",
                    "description": "How many days of news to fetch (default 30)",
                    "default": 30,
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_sector_context",
        "description": (
            "Get sector-level data and peer comparison for a ticker — "
            "sector P/E, median metrics, and how this ticker compares to peers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol",
                },
                "sector": {
                    "type": "string",
                    "description": "Sector name (e.g. 'Technology', 'Healthcare')",
                },
            },
            "required": ["ticker", "sector"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

async def execute_tool(tool_name: str, tool_input: dict) -> str:
    """
    Execute a named tool call and return a JSON string result.

    All data-fetching functions are synchronous and run in a thread pool
    via asyncio.to_thread so they don't block the event loop.
    """
    try:
        if tool_name == "get_price_history":
            from services.data_fetcher import get_price_history
            result = await asyncio.to_thread(
                get_price_history,
                tool_input["ticker"],
                tool_input.get("period", "1y"),
            )
            # Omit the full OHLCV records to keep context size manageable
            result_summary = {k: v for k, v in result.items() if k != "data"}
            result_summary["num_data_points"] = len(result.get("data", []))
            return json.dumps(result_summary, default=str)

        elif tool_name == "get_fundamentals":
            from services.data_fetcher import get_fundamentals
            result = await asyncio.to_thread(get_fundamentals, tool_input["ticker"])
            return json.dumps(result, default=str)

        elif tool_name == "search_sec_filings":
            from services.rag_service import get_rag_service
            rag = get_rag_service()
            ticker = tool_input["ticker"]

            # Ensure ticker is ingested first
            if not rag.is_ingested(ticker):
                logger.info(f"Triggering ingestion for {ticker} before search")
                await asyncio.to_thread(rag.ingest_ticker, ticker)

            results = await asyncio.to_thread(
                rag.search,
                ticker,
                tool_input["query"],
                tool_input.get("top_k", 4),
            )
            return json.dumps(results, default=str)

        elif tool_name == "get_news_sentiment":
            from services.data_fetcher import get_news_sentiment
            result = await asyncio.to_thread(get_news_sentiment, tool_input["ticker"])
            return json.dumps(result, default=str)

        elif tool_name == "get_sector_context":
            from services.data_fetcher import get_fundamentals, get_sector_peers
            ticker = tool_input["ticker"]
            sector = tool_input["sector"]

            peers = await asyncio.to_thread(get_sector_peers, sector)
            # Sample up to 5 peers, excluding the target ticker
            sample = [p for p in peers if p.upper() != ticker.upper()][:5]

            peer_data: list[dict[str, Any]] = []
            for peer in sample:
                try:
                    fd = await asyncio.to_thread(get_fundamentals, peer)
                    peer_data.append({
                        "ticker": peer,
                        "pe_ratio": fd.get("pe_ratio"),
                        "pb_ratio": fd.get("pb_ratio"),
                        "ev_ebitda": fd.get("ev_ebitda"),
                        "gross_margin": fd.get("gross_margin"),
                        "operating_margin": fd.get("operating_margin"),
                        "revenue_growth_yoy": fd.get("revenue_growth_yoy"),
                        "dividend_yield": fd.get("dividend_yield"),
                    })
                except Exception as peer_err:
                    logger.warning(f"Skipping peer {peer}: {peer_err}")

            # Compute simple medians for available metrics
            def median(vals: list) -> float | None:
                clean = [v for v in vals if v is not None]
                if not clean:
                    return None
                clean.sort()
                mid = len(clean) // 2
                return clean[mid] if len(clean) % 2 else (clean[mid - 1] + clean[mid]) / 2

            pe_vals = [p.get("pe_ratio") for p in peer_data]
            pb_vals = [p.get("pb_ratio") for p in peer_data]
            ev_vals = [p.get("ev_ebitda") for p in peer_data]

            return json.dumps({
                "ticker": ticker,
                "sector": sector,
                "sector_median_pe": median(pe_vals),
                "sector_median_pb": median(pb_vals),
                "sector_median_ev_ebitda": median(ev_vals),
                "peers": peer_data,
            }, default=str)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
        return json.dumps({"error": str(e), "tool": tool_name})
