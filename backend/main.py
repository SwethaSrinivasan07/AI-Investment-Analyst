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
from models.database import init_db, settings

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
    - Future: start APScheduler for scheduled memo generation
    """
    logger.info("Starting AlphaLens API...")
    await init_db()
    logger.info("Database initialised.")

    yield  # app is running

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
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
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


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "alphalens-api"}
