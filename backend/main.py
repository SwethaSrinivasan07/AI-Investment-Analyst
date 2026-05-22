"""
AlphaLens API — FastAPI application entry point.

Run with:
    cd backend && source venv/bin/activate
    uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
# override=True forces .env values to win over any empty/stale OS env vars
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth import router as auth_router
from api.chat import router as chat_router
from api.memos import router as memos_router
from api.stocks import router as stocks_router
from models.database import init_db, settings
from services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    - Initialises the SQLite database (creates tables if they don't exist)
    - Starts the APScheduler for scheduled memo generation
    """
    logger.info("Starting AlphaLens API...")
    await init_db()
    logger.info("Database initialised.")
    await start_scheduler()
    logger.info("Scheduler started.")

    yield  # app is running

    await stop_scheduler()
    logger.info("Shutting down AlphaLens API.")


app = FastAPI(
    title="AlphaLens API",
    description=(
        "Personal AI investment analyst. "
        "For educational purposes only — not financial advice."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# FRONTEND_URL may be a single URL or a comma-separated list, e.g.:
#   https://alphalens.pages.dev,http://localhost:3000
# ---------------------------------------------------------------------------
# Always include the production Vercel URL + localhost for dev
_ALWAYS_ALLOWED = [
    "https://ai-investment-analyst-blond.vercel.app",
    "http://localhost:3000",
    "http://localhost:3001",
]
_allowed_origins = list({
    *_ALWAYS_ALLOWED,
    *[o.strip() for o in settings.frontend_url.split(",") if o.strip()],
})
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(memos_router, prefix="/api/memos", tags=["memos"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(stocks_router, prefix="/api/stocks", tags=["stocks"])

# Optional routers — registered with a try/except so a missing file never
# prevents the rest of the app from starting while other agents build them.
try:
    from api.portfolio import router as portfolio_router
    app.include_router(portfolio_router, prefix="/api/portfolio", tags=["portfolio"])
except ImportError:
    logger.warning("portfolio router not yet available — skipping registration")

try:
    from api.backtests import router as backtests_router
    app.include_router(backtests_router, prefix="/api/backtests", tags=["backtests"])
except ImportError:
    logger.warning("backtests router not yet available — skipping registration")

try:
    from api.settings import router as settings_router
    app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
except ImportError:
    logger.warning("settings router not yet available — skipping registration")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "alphalens-api"}
