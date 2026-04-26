from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from pydantic_settings import BaseSettings

# Absolute path to .env — works regardless of process working directory.
# This file lives at backend/models/database.py, so .parent.parent = backend/
_ENV_FILE = str(Path(__file__).parent.parent / ".env")


class Settings(BaseSettings):
    anthropic_api_key: str
    alpha_vantage_api_key: str = ""
    sendgrid_api_key: str = ""
    jwt_secret: str
    database_url: str = "sqlite+aiosqlite:///./alphalens.db"
    chroma_persist_path: str = "./chroma_db"
    frontend_url: str = "http://localhost:3000"
    # Cost-control knobs read by agents via settings.*
    thinking_budget: int = 1024
    research_max_turns: int = 5

    class Config:
        env_file = _ENV_FILE
        env_file_encoding = "utf-8"


settings = Settings()

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add columns introduced after initial schema — safe to re-run (SQLite ignores duplicates)
        for stmt in [
            "ALTER TABLE memos ADD COLUMN usage_stats TEXT",
            "ALTER TABLE backtest_results ADD COLUMN strategy TEXT",  # backtest migration safety
        ]:
            try:
                await conn.execute(__import__('sqlalchemy').text(stmt))
            except Exception:
                pass  # column already exists
