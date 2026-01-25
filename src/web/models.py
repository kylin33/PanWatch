from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.web.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    name = Column(String, nullable=False)
    market = Column(String, nullable=False)  # CN / HK / US
    cost_price = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    agents = relationship("StockAgent", back_populates="stock", cascade="all, delete-orphan")


class StockAgent(Base):
    """多对多: 每只股票可被多个 Agent 监控"""
    __tablename__ = "stock_agents"
    __table_args__ = (UniqueConstraint("stock_id", "agent_name", name="uq_stock_agent"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String, nullable=False)  # 对应 AgentConfig.name
    schedule = Column(String, default="")  # cron 表达式，空则使用 Agent 全局配置
    created_at = Column(DateTime, server_default=func.now())

    stock = relationship("Stock", back_populates="agents")


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)  # agent 标识
    display_name = Column(String, nullable=False)
    description = Column(String, default="")
    enabled = Column(Boolean, default=True)
    schedule = Column(String, default="")  # cron 表达式
    ai_model = Column(String, default="")  # 为空则用全局配置
    ai_base_url = Column(String, default="")
    config = Column(JSON, default={})  # agent 特有配置
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String, nullable=False)
    status = Column(String, nullable=False)  # success / failed
    result = Column(String, default="")  # AI 分析结果
    error = Column(String, default="")
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    level = Column(String, nullable=False)
    logger_name = Column(String, default="")
    message = Column(String, default="")
    created_at = Column(DateTime, server_default=func.now())


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, default="")
    description = Column(String, default="")
