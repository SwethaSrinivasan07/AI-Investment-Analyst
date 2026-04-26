from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from .database import Base


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    preferences = Column(JSON, default=dict)  # {default_strategy, default_sector, schedule_frequency}

    memos = relationship("Memo", back_populates="user")
    schedules = relationship("UserSchedule", back_populates="user")
    portfolio = relationship("PortfolioPosition", back_populates="user")


class Memo(Base):
    __tablename__ = "memos"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    ticker = Column(String, nullable=False)
    company_name = Column(String)
    strategy = Column(String, nullable=False)  # momentum|value|growth|dividend
    sector = Column(String, nullable=False)
    recommendation = Column(String)  # Buy|Watch|Pass
    conviction = Column(String)  # High|Medium|Low
    markdown_text = Column(Text)
    thinking_trace = Column(JSON)  # list of thinking blocks
    sources = Column(JSON)  # list of source citations
    eval_scores = Column(JSON)  # {data_grounding, thesis_clarity, risk_depth, valuation_rigor, actionability}
    usage_stats = Column(JSON)  # {input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, estimated_cost_usd}
    data_as_of = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="memos")
    chat_history = relationship("MemoChatMessage", back_populates="memo")


class MemoChatMessage(Base):
    __tablename__ = "memo_chat_history"

    id = Column(String, primary_key=True, default=gen_uuid)
    memo_id = Column(String, ForeignKey("memos.id"), nullable=False)
    role = Column(String, nullable=False)  # user|assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    memo = relationship("Memo", back_populates="chat_history")


class UserSchedule(Base):
    __tablename__ = "user_schedules"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    strategy = Column(String, nullable=False)
    sector = Column(String, nullable=False)
    frequency = Column(String, nullable=False)  # daily|every2days|weekly
    enabled = Column(Boolean, default=True)
    next_run_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="schedules")


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    ticker = Column(String, nullable=False)
    shares = Column(Float, nullable=False)
    cost_basis = Column(Float, nullable=False)  # per share
    added_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="portfolio")


class AVCache(Base):
    __tablename__ = "alpha_vantage_cache"

    id = Column(String, primary_key=True, default=gen_uuid)
    ticker = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    response_data = Column(JSON, nullable=False)
    cached_at = Column(DateTime, default=datetime.utcnow)


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id = Column(String, primary_key=True, default=gen_uuid)
    strategy = Column(String, nullable=False)
    sector = Column(String, nullable=False)
    period = Column(String, nullable=False)  # "1y" | "2y"
    metrics = Column(JSON)  # {cumulative_return_pct, annualized_return_pct, sharpe_ratio, max_drawdown_pct, win_rate_pct, alpha_vs_spy_pct, volatility_pct}
    chart_data = Column(JSON)  # [{date, portfolio, spy, sector_etf}]
    created_at = Column(DateTime, default=datetime.utcnow)


class PortfolioAlert(Base):
    __tablename__ = "portfolio_alerts"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    ticker = Column(String)                   # null = portfolio-level alert
    alert_type = Column(String, nullable=False)  # price_move|news|signal|opportunity
    severity = Column(String, nullable=False)    # info|warning|action
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    data = Column(JSON)                       # {price_change_pct, signal, etc.}
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PortfolioOrder(Base):
    __tablename__ = "portfolio_orders"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    ticker = Column(String, nullable=False)
    side = Column(String, nullable=False)     # buy|sell
    qty = Column(Float, nullable=False)
    order_type = Column(String, default="market")
    status = Column(String, nullable=False)   # pending|submitted|filled|cancelled|rejected
    alpaca_order_id = Column(String)
    filled_price = Column(Float)
    source = Column(String, default="ai_signal")  # ai_signal|manual
    rationale = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    filled_at = Column(DateTime)
