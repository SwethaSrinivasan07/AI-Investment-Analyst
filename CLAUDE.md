# CLAUDE.md — AlphaLens

This file tells Claude Code how to work in this repository.

---

## Project Overview

**AlphaLens** is a personal AI investment analyst. It generates scheduled investment memos using a multi-agent Claude pipeline, grounded in live market data (Yahoo Finance, Alpha Vantage) and SEC filings retrieved via RAG (ChromaDB). Users pick a strategy (Momentum, Value, Growth, Dividend) and sector, and receive professional IC-format memos with extended thinking traces, source citations, and a chat interface to probe deeper.

- **Frontend:** Next.js 14 (app router), TypeScript, Tailwind CSS
- **Backend:** FastAPI (Python 3.11), APScheduler, SQLAlchemy (SQLite)
- **AI:** Claude API via `anthropic` Python SDK — model: `claude-sonnet-4-6`
- **AI Features:** Tool use, extended thinking, prompt caching, streaming (SSE)
- **Knowledge Layer:** ChromaDB vector store, sentence-transformers embeddings, SEC EDGAR + earnings call transcripts
- **Data:** `yfinance`, Alpha Vantage REST API, SEC EDGAR, BeautifulSoup for news
- **Auth:** JWT tokens, bcrypt password hashing

See `PRD.md` for full product requirements and architecture details.

---

## Repository Layout

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
│   ├── api/                   # Route handlers
│   │   ├── auth.py
│   │   ├── memos.py           # /generate, /stream, /list, /:id
│   │   ├── chat.py            # SSE streaming chat
│   │   ├── portfolio.py
│   │   └── backtests.py
│   ├── agents/                # Multi-agent pipeline
│   │   ├── orchestrator.py    # Coordinates the full pipeline
│   │   ├── screener_agent.py  # Quantitative ranking (no Claude)
│   │   ├── research_agent.py  # Tool-use + RAG agent
│   │   ├── bull_agent.py      # Bull case (extended thinking)
│   │   ├── bear_agent.py      # Bear case, adversarial (extended thinking)
│   │   ├── memo_writer.py     # Synthesis + IC memo (streaming + cached prompt)
│   │   └── eval_agent.py      # LLM-as-judge quality scorer
│   ├── services/
│   │   ├── data_fetcher.py    # yfinance + Alpha Vantage + scraping
│   │   ├── rag_service.py     # ChromaDB ingestion + retrieval
│   │   ├── backtester.py      # Strategy backtesting engine
│   │   ├── scheduler.py       # APScheduler cron jobs
│   │   └── emailer.py         # SendGrid integration
│   ├── tools/
│   │   └── financial_tools.py # Tool implementations callable by Claude
│   ├── models/                # SQLAlchemy ORM models
│   ├── prompts/               # All prompt templates (no inline prompts ever)
│   │   ├── system/
│   │   │   ├── research_agent.txt
│   │   │   ├── bull_agent.txt
│   │   │   ├── bear_agent.txt
│   │   │   ├── memo_writer.txt
│   │   │   └── eval_agent.txt
│   │   └── sector_knowledge/  # Per-sector primers (prompt-cached)
│   └── tests/
│
├── data/
│   ├── dummy_portfolio.json
│   └── sp500_tickers.csv
├── PRD.md
├── README.md
└── CLAUDE.md
```

---

## Key Development Guidelines

### Multi-Agent Pipeline

- All agents live in `backend/agents/`
- The `Orchestrator` in `orchestrator.py` is the only entry point — call `orchestrator.run(user_id, strategy, sector)` to kick off a full memo generation
- Never call individual agents directly from API routes
- Bull and Bear agents run in parallel using `asyncio.gather()` — do not make them sequential
- Each agent has a clearly defined `Input` and `Output` dataclass — never pass raw dicts between agents
- Agent state is not shared — agents communicate only through their output dataclasses passed by the orchestrator

### AI / Claude API

- Use `anthropic` SDK, model `claude-sonnet-4-6` for all generation tasks
- **Tool use:** Research Agent uses multi-turn tool calling. Tool implementations live in `backend/tools/financial_tools.py`. Tool definitions (JSON schema) live alongside each agent file.
- **Extended thinking:** Enable for Research Agent, Bull Agent, and Bear Agent. Use `thinking={"type": "enabled", "budget_tokens": 8000}`. Store the thinking trace in `memos.thinking_trace` (JSON array of thinking blocks).
- **Prompt caching:** Apply `cache_control: {"type": "ephemeral"}` to static system prompt blocks (sector knowledge, strategy definitions, IC memo format). Dynamic data (company-specific) is appended after the cached block — do NOT cache it.
- **Streaming:** Memo Writer Agent must stream. Use `client.messages.stream()` context manager. Emit SSE chunks from the FastAPI route. Never buffer the full memo before sending.
- All prompt templates live in `backend/prompts/` — do not hardcode prompts inline anywhere

### RAG Service

- `rag_service.py` manages ChromaDB — ingestion and retrieval
- Collection naming: `{ticker}_filings` (e.g., `ABBV_filings`)
- Chunk size: 512 tokens, 64-token overlap
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2` (runs locally, no API key)
- Always filter by `ticker` metadata at retrieval time — never retrieve cross-ticker
- Hybrid search: combine ChromaDB dense search with BM25 keyword scores (weight 0.7 dense / 0.3 sparse)
- All retrieved chunks must include source metadata: `{doc_type, filing_date, url, chunk_id}`
- The Memo Writer must cite sources inline using the format: `[Source: ABBV 10-K 2025, Risk Factors]`

### Data Fetching

- Primary: `yfinance` for price history, financials, balance sheet, income statement
- Secondary: Alpha Vantage for earnings estimates and company overview
- Supplementary: SEC EDGAR API (`https://data.sec.gov/`) for filings ingestion
- **Rate limits:** Alpha Vantage free tier = 25 req/day. Cache ALL AV responses in `alpha_vantage_cache` table with 24hr TTL. Check cache before every AV call.
- Always attach `as_of_date` to any data stored or passed to Claude

### Backtester

- Lives in `backend/services/backtester.py`
- Must use point-in-time data — use SEC filing dates as the fundamental availability date to avoid look-ahead bias
- Rebalancing frequency: weekly (configurable)
- Universe: S&P 500 (from `data/sp500_tickers.csv`)
- Benchmark: SPY total return
- Output: `BacktestResult` dataclass with metrics dict + chart data (JSON-serializable for frontend)

### Eval Agent

- Lives in `backend/agents/eval_agent.py`
- Runs automatically after every memo generation (async, non-blocking — does not delay memo delivery)
- Scores 5 dimensions: data_grounding, thesis_clarity, risk_depth, valuation_rigor, actionability
- Each dimension: score (1–5, float), rationale (string)
- Store results in `eval_results` table, linked to `memo_id`
- The Eval Agent must NOT see the thinking traces — it scores only the final memo text

### Database

- SQLite for MVP. Use SQLAlchemy ORM.
- Never write raw SQL strings — always use ORM queries
- Migrations via Alembic (`alembic upgrade head` to apply)
- Key tables: `users`, `memos`, `memo_chat_history`, `user_schedules`, `portfolio_positions`, `research_packs`, `backtest_results`, `eval_results`, `rag_documents`, `alpha_vantage_cache`

### Auth

- JWT issued at login, stored in `httpOnly` cookie on the frontend
- Backend validates JWT on all protected routes via `Depends(get_current_user)`
- Passwords hashed with `bcrypt` — never store plaintext

### Scheduler

- APScheduler configured in `backend/services/scheduler.py`
- One job per user schedule stored in `user_schedules` table
- Jobs trigger `orchestrator.run()` → `emailer.send_memo_email()`
- Scheduler starts with the FastAPI app via `lifespan` event

### Frontend

- App Router (Next.js 14), TypeScript strict mode
- Tailwind CSS for styling — no custom CSS files unless absolutely necessary
- `ThinkingTrace.tsx`: collapsible component showing extended thinking blocks, rendered differently from memo text (monospace, lighter style)
- `SourcesPanel.tsx`: sidebar/drawer showing all RAG citations for a memo, each linkable to the original SEC filing
- Chat UI: SSE streaming via `EventSource`
- Memo display: `react-markdown` with syntax highlighting
- Backtesting charts: Recharts (line chart, drawdown chart)
- All API calls go through `frontend/lib/api.ts` — never call backend directly from components

---

## Running Locally

```bash
# Backend
cd backend && source venv/bin/activate
uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Initialize vector store (first run only)
cd backend && python -m services.rag_service --ingest --tickers AAPL,MSFT,ABBV
```

---

## Environment Variables

All secrets go in `.env` (backend) and `.env.local` (frontend). Never commit these files.

Required backend vars:
- `ANTHROPIC_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `SENDGRID_API_KEY`
- `JWT_SECRET`
- `DATABASE_URL` (default: `sqlite:///./alphalens.db`)
- `CHROMA_PERSIST_PATH` (default: `./chroma_db`)

---

## Testing

- Backend: `pytest backend/tests/`
- Prefer integration tests over unit tests for screener and data fetcher
- Mock Claude API responses in tests using recorded fixtures (do not call the real API in CI)
- Test the full agent pipeline with a fixture `ResearchPack` — do not run live data fetches in tests
- Frontend: `npm test` (Jest + React Testing Library)

---

## Disclaimer

This project is for educational purposes only. Generated investment memos are not financial advice. Ensure all UI surfaces include the disclaimer: *"For educational use only. Not financial advice."*
