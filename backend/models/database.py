from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    alpha_vantage_api_key: str = ""
    sendgrid_api_key: str = ""
    jwt_secret: str
    database_url: str = "sqlite+aiosqlite:///./alphalens.db"
    chroma_persist_path: str = "./chroma_db"
    frontend_url: str = "http://localhost:3000"
    # Cost-control knobs (read by agents via os.getenv; declared here so
    # pydantic-settings doesn't reject them as extra fields)
    thinking_budget: int = 1024
    research_max_turns: int = 5

    class Config:
        env_file = ".env"


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
