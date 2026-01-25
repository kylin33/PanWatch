"""PanWatch 统一服务入口 - Web 后台 + Agent 调度"""
import logging
import os
import asyncio
from contextlib import asynccontextmanager

import uvicorn

from src.web.database import init_db, SessionLocal
from src.web.models import AgentConfig, Stock, StockAgent
from src.web.log_handler import DBLogHandler
from src.config import Settings, AppConfig, StockConfig
from src.models.market import MarketCode
from src.core.ai_client import AIClient
from src.core.notifier import NotifierManager, TelegramNotifier
from src.core.scheduler import AgentScheduler
from src.agents.base import AgentContext
from src.agents.daily_report import DailyReportAgent

logger = logging.getLogger(__name__)

# 全局 scheduler 实例，供 agents API 调用
scheduler: AgentScheduler | None = None


def setup_ssl():
    """设置 SSL 证书环境（企业代理环境）"""
    settings = Settings()
    ca_cert = settings.ca_cert_file
    if not ca_cert or not os.path.exists(ca_cert):
        return

    import certifi

    bundle_path = os.path.join(os.path.dirname(__file__), "data", "ca-bundle.pem")
    os.makedirs(os.path.dirname(bundle_path), exist_ok=True)

    need_rebuild = (
        not os.path.exists(bundle_path)
        or os.path.getmtime(ca_cert) > os.path.getmtime(bundle_path)
    )

    if need_rebuild:
        with open(bundle_path, "w") as out:
            with open(certifi.where(), "r") as f:
                out.write(f.read())
            out.write("\n")
            with open(ca_cert, "r") as f:
                out.write(f.read())

    os.environ["SSL_CERT_FILE"] = bundle_path
    os.environ["REQUESTS_CA_BUNDLE"] = bundle_path
    logger.info(f"SSL 证书已加载: {bundle_path}")


def setup_logging():
    """配置日志收集到数据库"""
    handler = DBLogHandler(level=logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def seed_agents():
    """初始化内置 Agent 配置"""
    db = SessionLocal()
    agents = [
        {
            "name": "daily_report",
            "display_name": "盘后日报",
            "description": "每日收盘后生成自选股日报，包含大盘概览、个股分析和明日关注",
            "enabled": True,
            "schedule": "30 15 * * 1-5",
        },
        {
            "name": "intraday_monitor",
            "display_name": "盘中监控",
            "description": "交易时段定时分析自选股，异动时主动通知",
            "enabled": False,
            "schedule": "*/30 9-15 * * 1-5",
        },
        {
            "name": "news_digest",
            "display_name": "新闻速递",
            "description": "定时抓取与持仓相关的新闻资讯并推送摘要",
            "enabled": False,
            "schedule": "0 */2 9-18 * * 1-5",
        },
        {
            "name": "morning_brief",
            "display_name": "开盘前瞻",
            "description": "每日开盘前分析隔夜外盘和新闻，给出今日关注点",
            "enabled": False,
            "schedule": "0 9 * * 1-5",
        },
    ]

    for agent_data in agents:
        existing = db.query(AgentConfig).filter(AgentConfig.name == agent_data["name"]).first()
        if not existing:
            db.add(AgentConfig(**agent_data))

    db.commit()
    db.close()


def load_watchlist_for_agent(agent_name: str) -> list[StockConfig]:
    """从数据库加载某个 Agent 关联的自选股"""
    db = SessionLocal()
    try:
        stock_agents = db.query(StockAgent).filter(StockAgent.agent_name == agent_name).all()
        stock_ids = [sa.stock_id for sa in stock_agents]
        if not stock_ids:
            return []

        stocks = db.query(Stock).filter(Stock.id.in_(stock_ids), Stock.enabled == True).all()
        result = []
        for s in stocks:
            try:
                market = MarketCode(s.market)
            except ValueError:
                market = MarketCode.CN
            result.append(StockConfig(
                symbol=s.symbol,
                name=s.name,
                market=market,
                cost_price=s.cost_price,
                quantity=s.quantity,
            ))
        return result
    finally:
        db.close()


def build_context(agent_name: str) -> AgentContext:
    """为指定 Agent 构建运行上下文"""
    settings = Settings()
    watchlist = load_watchlist_for_agent(agent_name)

    ai_client = AIClient(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        proxy=settings.http_proxy,
    )

    notifier = NotifierManager()
    if settings.notify_telegram_bot_token:
        notifier.add(TelegramNotifier(
            bot_token=settings.notify_telegram_bot_token,
            chat_id=settings.notify_telegram_chat_id,
            proxy=settings.http_proxy,
            ca_cert=os.environ.get("SSL_CERT_FILE", ""),
        ))

    config = AppConfig(settings=settings, watchlist=watchlist)
    return AgentContext(ai_client=ai_client, notifier=notifier, config=config)


# Agent 注册表
AGENT_REGISTRY: dict[str, type] = {
    "daily_report": DailyReportAgent,
}


def build_scheduler() -> AgentScheduler:
    """构建调度器并注册已启用的 Agent"""
    sched = AgentScheduler()

    db = SessionLocal()
    try:
        agent_configs = db.query(AgentConfig).filter(AgentConfig.enabled == True).all()
        for cfg in agent_configs:
            agent_cls = AGENT_REGISTRY.get(cfg.name)
            if not agent_cls:
                continue
            if not cfg.schedule:
                continue

            agent_instance = agent_cls()
            # 创建带动态 context 的包装
            context = build_context(cfg.name)
            sched.set_context(context)
            sched.register(agent_instance, cron=cfg.schedule)
    finally:
        db.close()

    return sched


async def trigger_agent(agent_name: str) -> str:
    """手动触发 Agent 执行（所有关联股票）"""
    agent_cls = AGENT_REGISTRY.get(agent_name)
    if not agent_cls:
        raise ValueError(f"Agent {agent_name} 未注册实际实现")

    context = build_context(agent_name)
    agent = agent_cls()

    watchlist = context.watchlist
    if not watchlist:
        return f"Agent {agent_name} 没有关联的自选股"

    result = await agent.run(context)
    return result.content


async def trigger_agent_for_stock(agent_name: str, stock) -> str:
    """手动触发 Agent 执行（单只股票）"""
    agent_cls = AGENT_REGISTRY.get(agent_name)
    if not agent_cls:
        raise ValueError(f"Agent {agent_name} 未注册实际实现")

    settings = Settings()
    try:
        market = MarketCode(stock.market)
    except ValueError:
        market = MarketCode.CN

    stock_config = StockConfig(
        symbol=stock.symbol,
        name=stock.name,
        market=market,
        cost_price=stock.cost_price,
        quantity=stock.quantity,
    )

    ai_client = AIClient(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        proxy=settings.http_proxy,
    )

    notifier = NotifierManager()
    if settings.notify_telegram_bot_token:
        notifier.add(TelegramNotifier(
            bot_token=settings.notify_telegram_bot_token,
            chat_id=settings.notify_telegram_chat_id,
            proxy=settings.http_proxy,
            ca_cert=os.environ.get("SSL_CERT_FILE", ""),
        ))

    config = AppConfig(settings=settings, watchlist=[stock_config])
    context = AgentContext(ai_client=ai_client, notifier=notifier, config=config)
    agent = agent_cls()

    result = await agent.run(context)
    return result.content


@asynccontextmanager
async def lifespan(app):
    """应用生命周期: 启动调度器"""
    global scheduler
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("Agent 调度器已启动")
    yield
    scheduler.shutdown()
    logger.info("Agent 调度器已关闭")


if __name__ == "__main__":
    init_db()
    setup_logging()
    setup_ssl()
    seed_agents()

    # 注入 lifespan 到 app
    from src.web.app import app
    app.router.lifespan_context = lifespan

    print("盯盘侠启动: http://127.0.0.1:8000")
    print("API 文档: http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
