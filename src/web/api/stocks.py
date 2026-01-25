import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.web.database import get_db
from src.web.models import Stock, StockAgent, AgentConfig
from src.web.stock_list import search_stocks, refresh_stock_list

logger = logging.getLogger(__name__)
router = APIRouter()


class StockCreate(BaseModel):
    symbol: str
    name: str
    market: str = "CN"
    cost_price: float | None = None
    quantity: int | None = None


class StockUpdate(BaseModel):
    name: str | None = None
    cost_price: float | None = None
    quantity: int | None = None
    enabled: bool | None = None


class StockAgentInfo(BaseModel):
    agent_name: str
    schedule: str = ""


class StockResponse(BaseModel):
    id: int
    symbol: str
    name: str
    market: str
    cost_price: float | None
    quantity: int | None
    enabled: bool
    agents: list[StockAgentInfo] = []

    class Config:
        from_attributes = True


class StockAgentItem(BaseModel):
    agent_name: str
    schedule: str = ""


class StockAgentUpdate(BaseModel):
    agents: list[StockAgentItem]


def _stock_to_response(stock: Stock) -> dict:
    return {
        "id": stock.id,
        "symbol": stock.symbol,
        "name": stock.name,
        "market": stock.market,
        "cost_price": stock.cost_price,
        "quantity": stock.quantity,
        "enabled": stock.enabled,
        "agents": [{"agent_name": sa.agent_name, "schedule": sa.schedule or ""} for sa in stock.agents],
    }


@router.get("/search")
def search(q: str = Query("", min_length=1), market: str = Query("")):
    """模糊搜索股票(代码/名称)"""
    return search_stocks(q, market)


@router.post("/refresh-list")
def refresh_list():
    """刷新股票列表缓存"""
    stocks = refresh_stock_list()
    return {"count": len(stocks)}


@router.get("", response_model=list[StockResponse])
def list_stocks(db: Session = Depends(get_db)):
    stocks = db.query(Stock).all()
    return [_stock_to_response(s) for s in stocks]


@router.post("", response_model=StockResponse)
def create_stock(stock: StockCreate, db: Session = Depends(get_db)):
    existing = db.query(Stock).filter(
        Stock.symbol == stock.symbol, Stock.market == stock.market
    ).first()
    if existing:
        raise HTTPException(400, f"股票 {stock.symbol} 已存在")

    db_stock = Stock(**stock.model_dump())
    db.add(db_stock)
    db.commit()
    db.refresh(db_stock)
    return _stock_to_response(db_stock)


@router.put("/{stock_id}", response_model=StockResponse)
def update_stock(stock_id: int, stock: StockUpdate, db: Session = Depends(get_db)):
    db_stock = db.query(Stock).filter(Stock.id == stock_id).first()
    if not db_stock:
        raise HTTPException(404, "股票不存在")

    for key, value in stock.model_dump(exclude_unset=True).items():
        setattr(db_stock, key, value)

    db.commit()
    db.refresh(db_stock)
    return _stock_to_response(db_stock)


@router.delete("/{stock_id}")
def delete_stock(stock_id: int, db: Session = Depends(get_db)):
    db_stock = db.query(Stock).filter(Stock.id == stock_id).first()
    if not db_stock:
        raise HTTPException(404, "股票不存在")
    db.delete(db_stock)
    db.commit()
    return {"ok": True}


@router.put("/{stock_id}/agents", response_model=StockResponse)
def update_stock_agents(stock_id: int, body: StockAgentUpdate, db: Session = Depends(get_db)):
    """更新股票关联的 Agent 列表（含调度配置）"""
    db_stock = db.query(Stock).filter(Stock.id == stock_id).first()
    if not db_stock:
        raise HTTPException(404, "股票不存在")

    # 验证 agent_names 是否存在
    for item in body.agents:
        agent = db.query(AgentConfig).filter(AgentConfig.name == item.agent_name).first()
        if not agent:
            raise HTTPException(400, f"Agent {item.agent_name} 不存在")

    # 清除旧关联，重建
    db.query(StockAgent).filter(StockAgent.stock_id == stock_id).delete()
    for item in body.agents:
        db.add(StockAgent(stock_id=stock_id, agent_name=item.agent_name, schedule=item.schedule))

    db.commit()
    db.refresh(db_stock)
    return _stock_to_response(db_stock)


@router.post("/{stock_id}/agents/{agent_name}/trigger")
async def trigger_stock_agent(stock_id: int, agent_name: str, db: Session = Depends(get_db)):
    """手动触发某只股票的指定 Agent"""
    db_stock = db.query(Stock).filter(Stock.id == stock_id).first()
    if not db_stock:
        raise HTTPException(404, "股票不存在")

    sa = db.query(StockAgent).filter(
        StockAgent.stock_id == stock_id, StockAgent.agent_name == agent_name
    ).first()
    if not sa:
        raise HTTPException(400, f"股票未关联 Agent {agent_name}")

    logger.info(f"手动触发 Agent {agent_name} - {db_stock.name}({db_stock.symbol})")

    from server import trigger_agent_for_stock
    try:
        result = await trigger_agent_for_stock(agent_name, db_stock)
        logger.info(f"Agent {agent_name} 执行完成 - {db_stock.symbol}")
        return {"result": result}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Agent {agent_name} 执行失败 - {db_stock.symbol}: {e}")
        raise HTTPException(500, f"Agent 执行失败: {e}")
