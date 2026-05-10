# AlphaLens — Personal AI Investment Analyst

> A multi-agent AI system that generates professional investment memos grounded in live market data, SEC filings, and adversarial reasoning. Built on Claude with tool use, extended thinking, RAG, and streaming.

AlphaLens screens stocks using momentum, value, growth, or dividend strategies across all 11 S&P 500 sectors, then runs them through a pipeline of specialized AI agents to produce full institutional-quality investment memos. Every claim is sourced from real financial data and SEC filings. Users can read the AI's reasoning trace, explore source documents, chat with the analyst, and see historical strategy performance.

---

## Architecture

```
User / Scheduler
       │
       ▼
  Orchestrator
       │
  ┌────┼────┐
  │    │    │
  ▼    ▼    ▼
Screener  Research Agent     ← tool use + RAG over SEC filings
Agent     (tool-use loop)
               │
          ┌────┴────┐
          │         │
      Bull Agent  Bear Agent  ← parallel, independent, extended thinking
          │         │
          └────┬────┘
               ▼
          Memo Writer         ← streaming + prompt caching
               │
          Eval Agent          ← LLM-as-judge quality scoring
```

---

## What Makes This Different

| Feature | Why it matters |
|---------|----------------|
| **Multi-agent pipeline** | Each agent has a single job. Bull and Bear agents run in parallel — the bear case is never anchored by the bull case. |
| **Tool use** | Research Agent calls its own data tools (`get_price_history`, `search_sec_filings`, etc.) — Claude decides what to look up, not the programmer. |
| **RAG over SEC filings** | 10-K, 10-Q, 8-K filings and earnings call transcripts are vectorized in ChromaDB. Every factual claim in the memo traces back to a source. |
| **Extended thinking** | Claude's internal reasoning process is captured and displayed — users can see *how* the analyst reached its conclusion. |
| **Prompt caching** | Static context (sector knowledge, valuation frameworks) is cached. Reduces token cost by ~40-60% per memo. |
| **Streaming** | Memos stream token-by-token via SSE — 30-second generation feels instant. |
| **Backtesting engine** | Run strategies against 2 years of historical data. See cumulative returns vs. SPY. |
| **LLM-as-judge evals** | Every memo is scored on 5 dimensions after generation. Quality trends over time are tracked. |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Backend | FastAPI (Python 3.11) |
| AI Model | Claude (`claude-sonnet-4-6`) via Anthropic SDK |
| AI Features | Tool use, extended thinking, prompt caching, SSE streaming |
| Vector Store | ChromaDB (local, persistent) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2, runs locally) |
| Market Data | yfinance + Alpha Vantage (free tier) |
| Filings | SEC EDGAR API |
| Database | SQLite + SQLAlchemy + Alembic |
| Scheduler | APScheduler |
| Email | SendGrid |
| Auth | JWT + bcrypt |
| Charts | Recharts |

---

## Features

- **Strategy-aware screening** — Momentum, Value, Growth, Dividend/Income across all 11 GICS sectors
- **Full IC Memos** — Executive summary, financials, valuation, bull case, bear case, risk matrix, catalysts, sector context, strategy explainer
- **Adversarial reasoning** — Independent Bull and Bear agents, each writing without seeing the other's output
- **Extended thinking UI** — Toggle "Show Analyst Reasoning" to see Claude's reasoning chain
- **Source citations** — Every factual claim links back to its SEC filing or data source
- **Chat interface** — Ask follow-up questions; the AI has full memo + research context
- **Scheduled delivery** — Daily / every 2 days / weekly; memos delivered in-app + email
- **Backtesting** — Historical strategy performance vs. SPY benchmark with Sharpe, drawdown, alpha
- **Memo quality scores** — Automated LLM-as-judge evaluation on 5 dimensions
- **Portfolio tracker** — Dummy portfolio with AI Hold/Trim/Add recommendations

---

## Project Structure

```
alphalens/
├── frontend/               # Next.js application
│   ├── app/                # Routes (auth, dashboard, memo, portfolio, backtests, settings)
│   ├── components/         # MemoCard, ThinkingTrace, SourcesPanel, ChatPanel, BacktestChart
│   └── lib/api.ts          # Centralized API client
├── backend/
│   ├── agents/             # Orchestrator + 6 specialized agents
│   ├── services/           # Data fetcher, RAG service, backtester, scheduler, emailer
│   ├── tools/              # Financial tool implementations (callable by Claude)
│   ├── models/             # SQLAlchemy DB models
│   └── prompts/            # All prompt templates + sector knowledge base
├── data/
│   ├── dummy_portfolio.json
│   └── sp500_tickers.csv
├── PRD.md
├── README.md
└── CLAUDE.md
```

---

## Getting Started

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11 – 3.13 | Tested on 3.13 |
| Node.js | 18+ | |
| Anthropic API key | — | Required — generates all memos |
| Alpha Vantage API key | — | Required — free tier (25 req/day) |
| SendGrid API key | — | Optional — only needed for email delivery |

---

### 1. Clone the repo

```bash
git clone https://github.com/SwethaSrinivasan07/AI-Investment-Analyst.git
cd AI-Investment-Analyst
```

---

### 2. Backend setup

> **macOS note:** If the repo lives inside an iCloud or OneDrive folder, create the virtual environment *outside* that folder to avoid macOS Gatekeeper blocking execution of synced binaries. The `~/alphalens-venv` path below works for everyone.

```bash
# Create venv outside any cloud-synced folder
python3 -m venv ~/alphalens-venv
source ~/alphalens-venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Copy and fill in environment variables
cp backend/.env.example backend/.env
# → Edit backend/.env and add your API keys (see table below)

# Initialize the database
cd backend
alembic upgrade head

# Ingest SEC filings into the vector store (first run only — takes ~3 min)
python -m services.rag_service --ingest --tickers AAPL,MSFT,ABBV,JPM,XOM

# Start the API server
~/alphalens-venv/bin/uvicorn main:app --reload --port 8000
```

You should see `Application startup complete.` in the terminal.

---

### 3. Frontend setup

```bash
cd frontend
npm install

# macOS only — clear Gatekeeper quarantine on native binaries
xattr -rd com.apple.quarantine node_modules

cp .env.local.example .env.local
# → .env.local is pre-filled correctly; no changes needed for local dev

npm run dev
# → Open http://localhost:3000
```

> **Port conflict?** If port 3000 is taken, find and kill the occupying process first:
> ```bash
> lsof -ti :3000 | xargs kill
> ```
> The backend CORS config expects port 3000. If you run the frontend on a different port, update `FRONTEND_URL` in `backend/.env` to match.

---

### 4. Environment variables

**`backend/.env`** (copy from `.env.example`):

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | Your Anthropic API key (`sk-ant-...`) |
| `ALPHA_VANTAGE_API_KEY` | ✅ | Free key from alphavantage.co |
| `SENDGRID_API_KEY` | Optional | Only needed for scheduled email delivery |
| `JWT_SECRET` | ✅ | Any random 32+ character string |
| `DATABASE_URL` | ✅ | Default: `sqlite+aiosqlite:///./alphalens.db` |
| `CHROMA_PERSIST_PATH` | ✅ | Default: `./chroma_db` |
| `FRONTEND_URL` | ✅ | Default: `http://localhost:3000` |
| `THINKING_BUDGET` | — | Tokens for extended thinking. `0` = off (~$0.08/memo), `1024` = default (~$0.18/memo), `5000` = full (~$0.37/memo) |
| `RESEARCH_MAX_TURNS` | — | Tool-use turns for Research Agent. Default: `5` |

**`frontend/.env.local`** (copy from `.env.local.example`):

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

### 5. Generate your first memo

1. Sign up at `http://localhost:3000/auth/signup`
2. Go to **Settings** and choose a strategy (e.g. Value) and sector (e.g. Healthcare)
3. Click **Generate Memo** on the Dashboard
4. Watch the memo stream in — the thinking trace, peer comparison table, and source citations will appear as it completes

---

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `operation not permitted: venv/bin/uvicorn` | macOS Gatekeeper blocking synced binary | Create venv at `~/alphalens-venv` (outside OneDrive/iCloud) |
| `Failed to load SWC binary` on `npm run dev` | Gatekeeper quarantined node_modules | Run `xattr -rd com.apple.quarantine node_modules` in `frontend/` |
| `Failed to fetch` on login | CORS mismatch — frontend port ≠ `FRONTEND_URL` | Kill whatever is on port 3000 (`lsof -ti :3000 \| xargs kill`) and restart frontend |
| `OPTIONS ... 400 Bad Request` in backend logs | Same CORS mismatch | Same fix as above |
| `Connection error during generation` in SSE | JWT token expired (7-day TTL) | Log out and log back in |
| `Could not import module "main"` | Wrong working directory | Make sure you `cd backend` before running uvicorn |
| Alpha Vantage data missing | 25 req/day free tier exhausted | Data falls back to yfinance automatically; wait until next day for AV cache to refresh |

---

## How It Works

1. **Configure** — Choose a strategy (Value, Momentum, Growth, Dividend) and sector (e.g., Healthcare)
2. **Screen** — Screener Agent ranks S&P 500 stocks by strategy-specific signals (P/E ratios, momentum scores, growth rates, dividend yields)
3. **Research** — Research Agent uses Claude with tool use to fetch exactly what it needs: price data, SEC filings, earnings transcripts, news sentiment
4. **Debate** — Bull Agent and Bear Agent independently write their cases using extended thinking — in parallel, without seeing each other's output
5. **Write** — Memo Writer synthesizes both cases into a full IC Memo, streaming the text to the UI in real-time
6. **Evaluate** — Eval Agent automatically scores the memo on 5 dimensions; score is stored for quality tracking
7. **Explore** — Read the memo, toggle the reasoning trace, explore source citations, chat to go deeper

---

## Investment Strategies

| Strategy | Key Signals |
|----------|-------------|
| **Momentum** | 3/6/12M price return, RSI 50–70, price vs. 50/200-day MA, relative sector strength |
| **Value** | P/E vs. sector median, P/B < 1.5, EV/EBITDA bottom tercile, positive FCF |
| **Growth** | Revenue growth > 15% YoY, EPS growth > 10%, PEG < 2, gross margin expansion |
| **Dividend** | Yield > 2.5%, payout ratio < 60%, ≥3-year growth streak, positive net income |

---

## Backtesting

Run strategy backtests from the "Performance" tab:
- **Lookback:** Up to 2 years of weekly rebalancing
- **Metrics:** Cumulative return, annualized return, Sharpe ratio, max drawdown, alpha vs. SPY
- **Caveats:** Transaction costs not modeled; survivorship bias present (S&P 500 only); past performance ≠ future results

---

## Disclaimer

AlphaLens is for **educational purposes only** and does not constitute financial advice. Always do your own research before making investment decisions. Results of the backtesting engine are simulated and hypothetical.

---

## Course Context

Built as part of the Frontier Labs course, MBA1, Spring 2026.  
**Report framing:** *How do you build a reliable, multi-agent AI system for high-stakes financial analysis?*  
Demonstrates: agentic system design, RAG, tool use, extended thinking, prompt caching, LLM evaluation.
