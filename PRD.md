# Product Requirements Document
## AlphaLens — Personal AI Investment Analyst

**Version:** 2.0  
**Date:** April 2026  
**Author:** Swetha Srinivasan  
**Status:** Final Draft  
**Report Framing:** AI System Design for High-Stakes Financial Decisions

---

## 1. Problem Statement

Active investing requires deep, time-consuming research: screening hundreds of stocks, interpreting financial statements, reading 10-Ks, synthesizing analyst reports, and deciding which strategy fits the current market. Most retail investors lack either the time or the analytical framework to do this consistently.

**Core pain points:**
- No time for deep fundamental or technical research
- Unclear how different strategies (momentum, value, growth, dividend) apply in practice
- No personalized, recurring signal grounded in real financial data
- Investment education is disconnected from live decisions
- Professional-grade tools (Bloomberg, FactSet) cost thousands per month

**Why AI, why now:** Large language models like Claude can read and reason over financial documents, synthesize across data sources, and produce structured analytical output. But using LLMs naively (one prompt, pre-loaded data) produces shallow, hallucination-prone output. The interesting design challenge is: *how do you build a reliable, multi-agent AI system that can be trusted for high-stakes financial analysis?*

This project explores that question in the context of a consumer investment product.

---

## 2. Vision

AlphaLens is a personal AI investment analyst that surfaces actionable investment ideas on a user-chosen schedule, tailored to a chosen strategy and sector. Every idea is produced by a pipeline of specialized AI agents — screener, researcher, bull, bear, and writer — grounded in real financial data and SEC filings. Ideas are delivered as structured investment committee (IC) memos. Users can chat with the AI to probe deeper, and over time the system tracks whether its strategies would have generated alpha.

> "Like having an investment research team that works nights and weekends, never stops reading, and explains its reasoning."

---

## 3. Target User

**Primary:** Business school students and early-career professionals who:
- Want to be more active investors but lack time for deep research
- Are interested in learning different investment strategies experientially
- Have some financial literacy but aren't full-time analysts
- Want to grow a portfolio with a mix of conviction and continuous learning

---

## 4. Goals & Success Metrics

| Goal | Metric |
|------|--------|
| Deliver high-quality, grounded memos | Memo eval score ≥ 4.0/5.0 across all quality dimensions |
| Reduce research time | Full memo generated in < 45 seconds end-to-end |
| Ground output in real data | ≥ 80% of factual claims in memo traceable to a source document |
| Demonstrate strategy value | Backtested strategy sharpe ratio > 0.5 on held-out period |
| Engage users through chat | ≥ 2 follow-up chat messages per memo on average |
| Show cost efficiency | Prompt caching reduces token cost by ≥ 40% vs. uncached baseline |

---

## 5. System Architecture Overview

AlphaLens is built around a **multi-agent pipeline** in which specialized agents handle discrete analytical tasks, coordinated by an orchestrator. This design separates concerns, enables parallelism, makes the system debuggable, and allows each agent to be evaluated and improved independently.

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER / SCHEDULER TRIGGER                      │
│              (strategy: Value, sector: Healthcare)                │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                               │
│   Coordinates agent pipeline, manages state, handles retries      │
└──┬──────────┬──────────┬──────────┬──────────┬──────────────────┘
   │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼
┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐
│Screen│  │Resear│  │ Bull │  │ Bear │  │ Memo │
│  er  │→ │  ch  │→ │Agent │→ │Agent │→ │Writer│
│Agent │  │Agent │  │      │  │      │  │Agent │
└──────┘  └──────┘  └──────┘  └──────┘  └──────┘
   │          │          │          │          │
   │          ▼          ▼          ▼          ▼
   │     ┌──────────────────────────────────────┐
   │     │          KNOWLEDGE LAYER              │
   │     │  RAG: SEC Filings + Earnings Calls    │
   │     │  Live Data: yfinance + Alpha Vantage  │
   │     │  News Sentiment: Scraped + scored     │
   │     └──────────────────────────────────────┘
   │
   ▼
┌──────────────┐
│   SCREENER   │
│  BACKTEST    │
│   ENGINE     │
└──────────────┘
```

---

## 6. Agent Specifications

### 6.1 Screener Agent

**Purpose:** Rank the stock universe by strategy-specific quantitative signals and return the top N candidates with their full data packages.

**Tools available:**
- `get_price_history(ticker, period)` → OHLCV from yfinance
- `get_fundamentals(ticker)` → P/E, P/B, EV/EBITDA, margins from yfinance
- `get_sector_peers(sector)` → list of tickers in the sector
- `compute_momentum_score(ticker)` → composite momentum signal
- `compute_value_score(ticker)` → composite value signal
- `compute_growth_score(ticker)` → composite growth signal
- `compute_dividend_score(ticker)` → composite dividend signal

**Output:** Ranked list of `{ticker, score, strategy_signals, data_package}` for the top 3–5 candidates.

**Strategy scoring logic:**

| Strategy | Signals | Weights |
|----------|---------|---------|
| Momentum | 3M return, 6M return, 12M return, RSI, price vs. 50/200 MA | 20/25/25/15/15 |
| Value | P/E vs. sector median, P/B, EV/EBITDA, FCF yield, earnings yield | 25/20/25/15/15 |
| Growth | Revenue growth YoY, EPS growth YoY, gross margin trend, PEG ratio | 30/30/25/15 |
| Dividend | Dividend yield, payout ratio (inverted), dividend growth streak, coverage ratio | 30/25/25/20 |

**Claude usage:** Minimal — this agent is primarily quantitative. Claude used only for edge-case tie-breaking with brief reasoning.

---

### 6.2 Research Agent

**Purpose:** For each top candidate from the Screener Agent, pull deep qualitative context: recent 10-K/10-Q filings, earnings call transcripts, news sentiment, and analyst consensus. Uses RAG to retrieve the most relevant passages from the knowledge layer.

**Tools available:**
- `search_sec_filings(ticker, query, top_k)` → retrieves relevant chunks from vectorized 10-K/10-Q
- `get_earnings_transcript_summary(ticker, quarter)` → key quotes and themes from last earnings call
- `get_news_sentiment(ticker, days=30)` → aggregated news sentiment score + headline summaries
- `get_analyst_consensus(ticker)` → buy/hold/sell distribution, median price target
- `get_balance_sheet(ticker)` → full balance sheet snapshot

**Output:** For each candidate, a `ResearchPack` — structured dict of quantitative data, RAG-retrieved passages, sentiment, and analyst context.

**Claude usage:** Tool-use mode. Claude is given the tools above and a research brief. It decides *which* tools to call and *what to query*, then synthesizes the results into a structured `ResearchPack`. This is the core agentic behavior — Claude drives its own research.

**Extended thinking:** Enabled at this stage. Claude's internal reasoning about what to look for and how to weigh conflicting signals is captured and stored (shown optionally in the UI as "analyst notes").

---

### 6.3 Bull Agent

**Purpose:** Write the affirmative investment case for the top-ranked candidate.

**Input:** `ResearchPack` from Research Agent

**Output:** Structured bull case covering:
- Core thesis (2–3 sentences)
- Key financial strengths (with specific data citations)
- Catalysts (near-term events that could re-rate the stock)
- Valuation support (why the current price is attractive)
- Comparable companies trading at premium multiples

**Claude usage:** Single Messages API call with the full `ResearchPack` as context. System prompt is prompt-cached (expensive static context about valuation frameworks, sector knowledge). Extended thinking enabled — reasoning trace stored.

---

### 6.4 Bear Agent

**Purpose:** Write an independent, adversarial bear case for the same candidate. Runs in parallel with the Bull Agent.

**Input:** Same `ResearchPack` from Research Agent

**Output:** Structured bear case covering:
- Core risk thesis
- Financial weaknesses or deteriorating trends
- Macro/sector headwinds
- Valuation risk (downside scenario)
- Red flags from SEC filings or earnings call language

**Claude usage:** Identical API setup to Bull Agent but with adversarial system prompt. The Bear Agent is *forbidden* from reading the Bull Agent's output — ensuring the cases are independent. Extended thinking enabled.

**Design note:** Running Bull and Bear in parallel (a) saves latency and (b) ensures the bear case isn't anchored by the bull case. This is a meaningful architectural choice worth discussing in the written report.

---

### 6.5 Memo Writer Agent

**Purpose:** Synthesize the Bull and Bear cases, all research data, and the user's strategy preferences into a full IC Memo.

**Input:** `ResearchPack` + `BullCase` + `BearCase` + `UserStrategy` + `UserPreferences`

**Output:** Full IC Memo in markdown (rendered in-app and formatted for email):

1. **Executive Summary** — Recommendation (Buy / Watch / Pass), conviction level (High/Medium/Low), 3-sentence thesis
2. **Company Snapshot** — Business model, revenue mix, competitive moat
3. **Investment Thesis** — Strategy fit explanation, why now
4. **Financial Deep Dive** — Key metrics table, trend analysis (3-year), margin trajectory
5. **Valuation Analysis** — DCF range, EV/EBITDA comps, implied upside/downside
6. **Bull Case** — Synthesized from Bull Agent, with key evidence
7. **Bear Case** — Synthesized from Bear Agent, with key evidence
8. **Catalysts** — Near-term events and their expected impact
9. **Risk Matrix** — Probability × impact grid for top 5 risks
10. **Sector Context** — Where this company fits in its sector right now
11. **Strategy Fit Explainer** — Educational section explaining why this stock scores well on the chosen strategy
12. **Data Sources & Confidence** — What data was used, freshness, and confidence flags

**Claude usage:** System prompt is prompt-cached (sector knowledge base, valuation frameworks, IC memo format instructions). Streaming enabled — memo text streams token by token to the frontend via SSE.

---

## 7. RAG Pipeline (Knowledge Layer)

### 7.1 Document Ingestion

**Sources ingested into vector store:**
| Source | Content | Update Frequency |
|--------|---------|-----------------|
| SEC EDGAR 10-K | Annual report: business overview, risk factors, MD&A | Annual |
| SEC EDGAR 10-Q | Quarterly report: interim financials, business updates | Quarterly |
| SEC 8-K | Material events, earnings releases | Real-time |
| Earnings call transcripts | Management commentary, analyst Q&A | Quarterly |
| News articles | Scraped from Yahoo Finance news, Google News | Daily |

**Ingestion pipeline:**
1. Fetch raw documents from SEC EDGAR API (`https://data.sec.gov/`) and scrapers
2. Parse to clean text (BeautifulSoup for HTML filings, pdfplumber for PDF)
3. Chunk: 512-token chunks with 64-token overlap
4. Embed: `text-embedding-3-small` (OpenAI) or a free alternative (`sentence-transformers/all-MiniLM-L6-v2`)
5. Store: ChromaDB (local vector store, no infra needed for MVP)
6. Index: `{ticker, doc_type, filing_date, chunk_id, text, embedding}`

### 7.2 Retrieval Strategy

**Query-time retrieval (used by Research Agent):**
1. Research Agent constructs a semantic query (e.g., `"revenue growth drivers and competitive moat for ABBV"`)
2. Retrieve top-K chunks by cosine similarity from vector store
3. Apply metadata filter: `ticker = "ABBV"` and `filing_date > 18 months ago`
4. Re-rank retrieved chunks by recency × relevance score
5. Pass top 5–8 chunks as context to the Research Agent

**Hybrid retrieval:** Combine dense (embedding) search with sparse (BM25 keyword) search — especially important for financial terms like specific metric names, product names, and regulatory references.

### 7.3 Grounding & Citation

Every factual claim in the final memo traces back to a source chunk. The Memo Writer Agent is instructed to cite sources inline (e.g., *"[Source: ABBV 10-K 2025, Risk Factors section]*"). This enables:
- A "Sources" panel in the UI where users can drill into the original document
- The eval framework to measure grounding rate (% of claims cited)

---

## 8. Extended Thinking Integration

Claude's extended thinking capability is used in the Research Agent and both the Bull and Bear Agents.

**How it works:** Claude is given a `thinking` budget (e.g., 8,000 tokens) before producing its final output. The internal reasoning chain is captured separately from the output.

**UI integration:**
- By default, the memo shows only the final synthesized output
- Users can toggle "Show Analyst Reasoning" to see the thinking trace — rendered in a collapsible side panel
- The thinking trace is stored in the DB alongside the memo for future reference

**Why this matters (for the report):** Extended thinking allows Claude to work through conflicting signals (e.g., strong momentum but deteriorating margins) in a principled way before committing to a recommendation. It also provides transparency into *why* the system made its call — a key requirement for any AI system used in high-stakes decisions.

---

## 9. Tool Use Architecture

Rather than pre-loading all data into the prompt (which is expensive, inflexible, and doesn't scale), the Research Agent uses Claude's native tool use to fetch exactly what it needs.

### Tool Definitions (provided to Claude via API)

```python
tools = [
    {
        "name": "get_price_history",
        "description": "Fetch OHLCV price history for a ticker from Yahoo Finance",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "period": {"type": "string", "enum": ["1mo", "3mo", "6mo", "1y", "2y", "5y"]}
            },
            "required": ["ticker", "period"]
        }
    },
    {
        "name": "search_sec_filings",
        "description": "Semantic search over SEC filings (10-K, 10-Q, 8-K) for a ticker",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "query": {"type": "string", "description": "Natural language search query"},
                "doc_types": {"type": "array", "items": {"type": "string"}},
                "top_k": {"type": "integer", "default": 5}
            },
            "required": ["ticker", "query"]
        }
    },
    {
        "name": "get_earnings_transcript",
        "description": "Get key excerpts from the most recent earnings call transcript",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "focus": {"type": "string", "description": "What to focus on (e.g., 'guidance', 'margin commentary', 'competitive dynamics')"}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_fundamentals",
        "description": "Fetch key financial ratios and metrics for a ticker",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "metrics": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_news_sentiment",
        "description": "Get aggregated news sentiment and headline summaries for a ticker",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "default": 30}
            },
            "required": ["ticker"]
        }
    }
]
```

**Agentic loop:** The Research Agent runs in a multi-turn tool use loop — it calls tools, receives results, reasons over them, calls more tools if needed, then produces its final `ResearchPack`. The loop runs for a maximum of 8 turns (configurable), with a timeout of 30 seconds.

---

## 10. Prompt Caching Strategy

Prompt caching reduces cost and latency by reusing expensive static context across requests.

### What gets cached

| Component | Cached Content | Cache TTL | Estimated tokens |
|-----------|---------------|-----------|-----------------|
| Memo Writer system prompt | IC memo format, valuation frameworks, sector knowledge base, writing style guide | 5 min | ~6,000 |
| Sector knowledge base | Detailed sector primers for all 11 GICS sectors | 5 min | ~12,000 |
| Strategy definitions | Full strategy scoring logic and interpretation guides | 5 min | ~3,000 |
| SEC filing context | Chunked 10-K/10-Q context per ticker (within a session) | 5 min | ~8,000 |

### Implementation

Use the `cache_control: {"type": "ephemeral"}` parameter on system prompt blocks with the Anthropic SDK. The sector knowledge base and strategy definitions are placed at the top of the system prompt as a static cached block, with dynamic data appended at the end (not cached).

**Expected savings:** For a typical memo generation run (5 agent calls), caching reduces input token cost by an estimated 40–60%.

---

## 11. Streaming Architecture

Memo text streams to the frontend as it is generated, using Server-Sent Events (SSE).

**Flow:**
1. Frontend initiates memo generation request (`POST /api/memos/generate`)
2. Backend starts the agent pipeline; the final Memo Writer Agent is called with `stream=True`
3. Backend streams token chunks via SSE: `data: {"delta": "...token..."}` 
4. Frontend uses `EventSource` to receive chunks and appends to the memo display in real-time
5. When stream ends, full memo text is saved to the database

**Why streaming matters:** For a ~3,000-word IC memo, generation takes 20–40 seconds. Streaming makes this feel instantaneous from the user's perspective — they see the memo appearing word by word. This is critical for demo quality.

**Streaming for chat:** The chat interface also streams, using the same SSE pattern. Conversation history is maintained in the DB and passed as context on each turn.

---

## 12. Strategy Backtesting Engine

### Overview

The backtesting engine answers: *"How would this strategy have performed historically?"*

Given a `(strategy, sector, lookback_period)` configuration, the engine:
1. Reconstructs the screener's historical rankings at weekly intervals over the lookback period
2. Simulates a simple long-only portfolio (equal-weight top 3 picks, rebalanced weekly)
3. Computes performance metrics vs. the SPY benchmark
4. Stores results in the DB for display in the Strategy Performance dashboard

### Data

- Price history from `yfinance` (up to 10 years of daily OHLCV)
- Fundamental data is **point-in-time** to avoid look-ahead bias (e.g., use the P/E ratio as it was *known* at the time of the trade, not the current ratio)
- Point-in-time fundamentals sourced from the SEC EDGAR API (filed dates are used as the availability dates)

### Performance Metrics

| Metric | Formula |
|--------|---------|
| Cumulative return | Total portfolio return over period |
| Annualized return | CAGR |
| Sharpe ratio | (Ann. return - risk-free rate) / Ann. volatility |
| Max drawdown | Largest peak-to-trough decline |
| Win rate | % of weekly rebalances that beat SPY |
| Alpha vs. SPY | Excess return over benchmark |
| Sector beta | Correlation with sector ETF |

### Visualization

- Line chart: portfolio cumulative return vs. SPY vs. sector ETF
- Drawdown chart: rolling max drawdown over time
- Rolling Sharpe: 12-week rolling Sharpe ratio
- Turnover heatmap: how often the top picks changed

### Limitations & Honest Caveats

The backtest has important limitations that should be disclosed:
- Transaction costs are not modeled (assume 0 bps — optimistic)
- Fundamental data point-in-time accuracy is approximate for older periods
- Small backtesting universe (S&P 500 only) — survivorship bias present
- Past performance does not predict future results

---

## 13. Evaluation Framework

A key differentiator of this project is that it treats memo quality as a measurable, improvable quantity — not a subjective judgment.

### 13.1 LLM-as-Judge

After every memo is generated, an independent `EvalAgent` scores it on 5 dimensions using a separate Claude call:

| Dimension | Definition | Scoring criteria |
|-----------|-----------|-----------------|
| **Data grounding** | Are factual claims supported by cited sources? | % of claims with citations; 1–5 scale |
| **Thesis clarity** | Is the investment thesis clear, specific, and falsifiable? | Presence of specific price targets, catalysts, timeline |
| **Risk depth** | Are risks identified, quantified, and addressed? | Number and specificity of risks; bear case quality |
| **Valuation rigor** | Is the valuation analysis sound and methodology explained? | DCF assumptions stated; comps cited; range provided |
| **Actionability** | Can a reader make a decision from this memo? | Clear recommendation; entry conditions stated |

**EvalAgent prompt:** The EvalAgent is given the memo text and a structured rubric. It is explicitly told *not* to consider writing style or length — only analytical quality. It returns a JSON score object.

### 13.2 Aggregate Quality Dashboard

- Per-memo quality scores stored in DB
- Aggregate quality trend over time (are memos getting better as the system is tuned?)
- Per-dimension breakdown (e.g., valuation rigor consistently lower than thesis clarity → prompt improvement target)
- A/B testing framework: compare memo quality with vs. without extended thinking, RAG vs. no RAG, etc.

### 13.3 Grounding Rate

Independently computed metric: for each factual claim in the memo (identified by pattern matching on financial figures, percentages, and named entities), check whether a source citation is present. Target: ≥ 80% grounding rate.

---

## 14. Core Product Features

### 14.1 Strategy & Sector Configuration

Users configure a "watchlist recipe":
- **Strategy:** Momentum, Value, Growth, Dividend/Income
- **Sector:** Any of the 11 GICS sectors
- **Universe:** S&P 500 (can expand to S&P 400 in v2)
- **Number of ideas:** 1–3 per memo (recommend 1 for quality depth)
- **Schedule:** Daily, Every 2 days, Weekly

### 14.2 Memo Display

- Full IC Memo rendered in-app using `react-markdown`
- Collapsible sections (each memo section can be expanded/collapsed)
- "Show Analyst Reasoning" toggle — reveals extended thinking trace
- "Sources" panel — lists all RAG-retrieved documents with links to originals
- Confidence indicators per section (High / Medium / Low — derived from data freshness and source availability)
- Print/PDF export

### 14.3 Chat Interface

After reading a memo, users chat with a contextual AI analyst:
- Full memo text + research pack + thinking traces are in context
- Streaming responses
- Chat history persisted per memo
- Example probes: "What's the bear case on margins?", "How does this compare to JNJ?", "Explain EV/EBITDA like I'm a first-year analyst"

### 14.4 Scheduled Delivery

- APScheduler cron jobs, one per user schedule
- Job: `run_pipeline(user_id, strategy, sector)` → `generate_memo()` → `email_memo()`
- Email: HTML-formatted memo via SendGrid
- In-app: new memo badge on dashboard

### 14.5 Portfolio Tracker (Mock)

- Pre-loaded dummy portfolio: ~10 positions across sectors
- Live P&L using yfinance prices
- AI analysis: for each position, the pipeline runs a focused research pass and outputs Hold/Trim/Add with a brief rationale
- Users can edit the dummy portfolio (add/remove positions, change cost basis)

### 14.6 Strategy Performance Dashboard

- Powered by the backtesting engine
- Shows historical performance of each strategy in each sector
- "If you had followed these signals..." framing
- Not presented as a guarantee — prominent disclaimer

---

## 15. Data Architecture

### 15.1 Data Sources

| Source | Data | Integration | Rate Limit |
|--------|------|-------------|------------|
| Yahoo Finance (`yfinance`) | Price history, financials, income statement, balance sheet | Python library, no API key | Generous, cache recommended |
| Alpha Vantage | Earnings estimates, company overview, technical indicators | REST API | 25 req/day (free tier) — cache all responses |
| SEC EDGAR | 10-K, 10-Q, 8-K filings | `https://data.sec.gov/` REST API | No stated limit — be respectful |
| Yahoo Finance News | News headlines and summaries | Scraped via `yfinance` or BeautifulSoup | Cache aggressively |
| S&P 500 tickers | Universe definition | Static CSV from Wikipedia | N/A |

### 15.2 Database Schema (SQLite → PostgreSQL in v2)

**Key tables:**

```
users                    → id, email, hashed_password, created_at, preferences_json
memos                    → id, user_id, ticker, strategy, sector, markdown_text, 
                           thinking_trace, eval_scores_json, data_as_of, created_at
memo_chat_history        → id, memo_id, role, content, created_at
user_schedules           → id, user_id, strategy, sector, frequency, next_run_at, enabled
portfolio_positions      → id, user_id, ticker, shares, cost_basis, added_at
research_packs           → id, ticker, strategy, data_json, created_at  (24hr cache)
backtest_results         → id, strategy, sector, period, metrics_json, chart_data_json, created_at
eval_results             → id, memo_id, dimension, score, rationale, created_at
rag_documents            → id, ticker, doc_type, filing_date, chunk_id, text, embedding_id
alpha_vantage_cache      → id, ticker, endpoint, response_json, cached_at  (24hr TTL)
```

### 15.3 Caching Strategy

| Data type | Cache TTL | Storage |
|-----------|-----------|---------|
| Price history (daily OHLCV) | 12 hours | SQLite |
| Fundamentals (P/E, ratios) | 24 hours | SQLite |
| Alpha Vantage responses | 24 hours | SQLite |
| SEC filings (parsed + chunked) | 90 days | ChromaDB |
| Generated memos | Never expire (versioned) | SQLite |
| Backtest results | 7 days | SQLite |
| News sentiment | 6 hours | SQLite |

---

## 16. Technical Stack

| Layer | Technology | Version | Rationale |
|-------|------------|---------|-----------|
| Frontend | Next.js (React) | 14 | App Router, SSR, SSE support, TypeScript |
| Backend | FastAPI (Python) | 0.110+ | Async, OpenAPI docs, easy integration with AI SDKs |
| AI | Anthropic `anthropic` SDK | Latest | Claude tool use, extended thinking, streaming, caching |
| AI Model | `claude-sonnet-4-6` | — | Best balance of quality, speed, cost for financial analysis |
| Vector Store | ChromaDB | Latest | Local, no infra, persistent, fast for MVP |
| Embeddings | `sentence-transformers` | Latest | Free, runs locally, good quality for financial text |
| Market Data | `yfinance` | Latest | Free, reliable, broad coverage |
| Supplemental Data | Alpha Vantage REST | — | Free tier sufficient with caching |
| Filings | SEC EDGAR API | — | Free, official government source |
| Database | SQLAlchemy + SQLite | — | Zero-config for MVP |
| Migrations | Alembic | — | Schema versioning |
| Scheduler | APScheduler | 3.x | Runs inside FastAPI via lifespan event |
| Email | SendGrid | — | Free tier: 100 emails/day |
| Auth | JWT + `bcrypt` | — | Standard, simple |
| Styling | Tailwind CSS | 3.x | No custom CSS needed |
| Markdown | `react-markdown` | — | Render Claude's memo output |
| Charts | Recharts | — | Backtesting visualizations |

---

## 17. Repository Layout

```
alphalens/
├── frontend/
│   ├── app/
│   │   ├── auth/              # Login / signup
│   │   ├── dashboard/         # Memo feed
│   │   ├── memo/[id]/         # Memo detail + chat + sources panel
│   │   ├── portfolio/         # Dummy portfolio + AI analysis
│   │   ├── backtests/         # Strategy performance dashboard
│   │   └── settings/          # Strategy, sector, schedule prefs
│   ├── components/
│   │   ├── MemoCard.tsx
│   │   ├── MemoDetail.tsx
│   │   ├── ThinkingTrace.tsx   # Collapsible extended thinking viewer
│   │   ├── SourcesPanel.tsx    # RAG source citations panel
│   │   ├── ChatPanel.tsx
│   │   ├── PortfolioTable.tsx
│   │   └── BacktestChart.tsx
│   └── lib/
│       └── api.ts             # All backend calls centralized here
│
├── backend/
│   ├── main.py                # FastAPI app + lifespan (scheduler start)
│   ├── api/
│   │   ├── auth.py
│   │   ├── memos.py           # /generate, /stream, /list, /:id
│   │   ├── chat.py            # SSE streaming chat
│   │   ├── portfolio.py
│   │   └── backtests.py
│   ├── agents/
│   │   ├── orchestrator.py    # Coordinates the full pipeline
│   │   ├── screener_agent.py  # Quantitative ranking
│   │   ├── research_agent.py  # Tool-use RAG agent
│   │   ├── bull_agent.py      # Bull case writer
│   │   ├── bear_agent.py      # Bear case writer (adversarial)
│   │   ├── memo_writer.py     # Synthesis + IC memo generation
│   │   └── eval_agent.py      # LLM-as-judge memo scorer
│   ├── services/
│   │   ├── data_fetcher.py    # yfinance + Alpha Vantage + scraping
│   │   ├── rag_service.py     # ChromaDB ingestion + retrieval
│   │   ├── backtester.py      # Strategy backtesting engine
│   │   ├── scheduler.py       # APScheduler cron jobs
│   │   └── emailer.py         # SendGrid integration
│   ├── tools/
│   │   └── financial_tools.py # Tool implementations (callable by Claude)
│   ├── models/                # SQLAlchemy ORM models
│   ├── prompts/               # All prompt templates (no inline prompts)
│   │   ├── system/
│   │   │   ├── research_agent.txt
│   │   │   ├── bull_agent.txt
│   │   │   ├── bear_agent.txt
│   │   │   ├── memo_writer.txt
│   │   │   └── eval_agent.txt
│   │   └── sector_knowledge/  # Per-sector knowledge base (cached)
│   │       ├── technology.txt
│   │       ├── healthcare.txt
│   │       └── ... (11 total)
│   └── tests/
│       ├── test_screener.py
│       ├── test_rag.py
│       ├── test_agents.py     # Uses recorded Claude fixtures
│       └── test_backtester.py
│
├── data/
│   ├── dummy_portfolio.json
│   └── sp500_tickers.csv
│
├── PRD.md
├── README.md
└── CLAUDE.md
```

---

## 18. Security & Compliance

- JWT stored in `httpOnly` cookies — not accessible to JavaScript
- Passwords hashed with `bcrypt` (cost factor 12)
- All secrets in `.env` / `.env.local` — never committed to git
- CORS restricted to `localhost:3000` in development; configured via env var in production
- Rate limiting on `/api/memos/generate` — max 5 requests/hour per user (prevent abuse + cost protection)
- Prominent disclaimer on all memo surfaces: *"For educational purposes only. Not financial advice."*

---

## 19. Phased Roadmap

### Phase 1 — MVP (Course Submission)
- [ ] FastAPI backend scaffolding + SQLite schema
- [ ] yfinance + Alpha Vantage data fetcher with caching
- [ ] Screener Agent for all 4 strategies
- [ ] SEC EDGAR ingestion + ChromaDB vector store
- [ ] Research Agent with tool use
- [ ] Bull + Bear Agents (parallel execution)
- [ ] Memo Writer Agent with streaming + prompt caching
- [ ] Extended thinking capture + UI display
- [ ] Next.js frontend: auth, dashboard, memo detail, chat
- [ ] Sources panel (RAG citation viewer)
- [ ] APScheduler + email delivery (SendGrid)
- [ ] Dummy portfolio with AI analysis
- [ ] Backtesting engine (basic version: 2-year lookback)
- [ ] LLM-as-judge eval framework

### Phase 2 — Post-Course
- [ ] Real brokerage integration (Alpaca paper trading)
- [ ] PostgreSQL migration
- [ ] More sophisticated point-in-time fundamentals (Tiingo or Quandl)
- [ ] Options overlay on equity picks
- [ ] Personalization memory (learn from user behavior)

### Phase 3 — Scale
- [ ] Multi-user with teams
- [ ] International equities (ADRs first)
- [ ] Community memos / shared watchlists
- [ ] API product (developers subscribe to the memo feed)

---

## 20. Written Report Outline

**Framing:** *"How do you build a reliable, multi-agent AI system for high-stakes financial analysis?"*

**Suggested sections:**
1. **Problem & Motivation** — Why retail investing is broken; why AI is the right solution now
2. **System Design** — The multi-agent pipeline: design decisions, trade-offs, and why each agent is separated
3. **Knowledge Grounding** — How RAG over SEC filings reduces hallucination; grounding rate results
4. **Extended Thinking** — What the reasoning trace reveals about model behavior; cases where it matters
5. **Evaluation** — LLM-as-judge methodology, results, what the scores mean
6. **Backtesting Results** — Strategy performance, Sharpe ratios, honest caveats
7. **Cost Analysis** — Token usage, prompt caching savings, cost per memo at scale
8. **Limitations & Future Work** — What the system can't do yet; real brokerage integration; survivorship bias
9. **Conclusion** — What this project demonstrates about the current state of AI for financial analysis

---

## 21. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| yfinance breaks / rate limits | Medium | High | Cache aggressively; fallback to Alpha Vantage |
| Alpha Vantage 25 req/day limit | High | Medium | Cache all responses for 24hr; mock data fallback |
| Claude API latency > 60s | Low | High | Streaming hides latency; timeout + retry logic |
| RAG retrieval quality low | Medium | High | Hybrid dense+sparse search; human eval spot-checks |
| Backtest look-ahead bias | Medium | High | Use SEC filing dates as fundamental availability dates |
| LLM-as-judge scores unreliable | Medium | Medium | Calibrate scores against human ratings on 20 memos |
| Extended thinking token cost | Medium | Medium | Budget cap (8K thinking tokens max); monitor spend |

---

## 22. Non-Functional Requirements

- Memo generation: < 45 seconds end-to-end (streaming makes this feel faster)
- Scheduled delivery accuracy: within 5 minutes of configured time
- RAG retrieval: < 500ms per query (ChromaDB local)
- App first load: < 2 seconds (Next.js SSR)
- All financial data clearly timestamped: "Data as of [date]"
- Mandatory disclaimer on every memo surface: *"AlphaLens is for educational purposes only and does not constitute financial advice."*

---

*This PRD is a living document. Last updated: April 2026.*
