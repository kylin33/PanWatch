"""股票列表缓存与模糊搜索"""
import json
import os
import time
import logging
import concurrent.futures

import httpx

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
CACHE_FILE = os.path.join(DATA_DIR, "stock_list_cache.json")
CACHE_TTL = 86400 * 7  # 7 days

EASTMONEY_URL = "http://80.push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_PARAMS = {
    "po": "1",
    "np": "1",
    "fltt": "2",
    "invt": "2",
    "fid": "f12",
    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
    "fields": "f12,f14",
}
PAGE_SIZE = 100


def _load_cache() -> list[dict] | None:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("ts", 0) < CACHE_TTL:
            return data["stocks"]
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _save_cache(stocks: list[dict]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({"ts": time.time(), "stocks": stocks}, f, ensure_ascii=False)


def _fetch_page(client: httpx.Client, page: int) -> list[dict]:
    """获取东方财富股票列表的单页"""
    params = {**EASTMONEY_PARAMS, "pn": str(page), "pz": str(PAGE_SIZE)}
    resp = client.get(EASTMONEY_URL, params=params, timeout=10)
    data = resp.json()
    diff = data.get("data") or {}
    items = diff.get("diff") or []
    return [{"symbol": str(item["f12"]), "name": str(item["f14"]), "market": "CN"} for item in items]


def _fetch_from_eastmoney() -> list[dict]:
    """东方财富 A 股列表（HTTP 分页并发获取）"""
    with httpx.Client() as client:
        # 第一页: 获取总数
        params = {**EASTMONEY_PARAMS, "pn": "1", "pz": str(PAGE_SIZE)}
        resp = client.get(EASTMONEY_URL, params=params, timeout=10)
        data = resp.json()
        root = data.get("data") or {}
        total = root.get("total", 0)
        first_items = root.get("diff") or []

        stocks = [{"symbol": str(item["f12"]), "name": str(item["f14"]), "market": "CN"} for item in first_items]

        if total <= PAGE_SIZE:
            return stocks

        # 剩余页并发获取
        pages_needed = (total + PAGE_SIZE - 1) // PAGE_SIZE
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch_page, client, pn): pn for pn in range(2, pages_needed + 1)}
            for future in concurrent.futures.as_completed(futures):
                try:
                    stocks.extend(future.result())
                except Exception as e:
                    logger.warning(f"东方财富第 {futures[future]} 页获取失败: {e}")

    return stocks


def _fetch_from_akshare() -> list[dict]:
    """akshare 数据源（备用，可能有 SSL 问题）"""
    import akshare as ak

    df = ak.stock_info_a_code_name()
    stocks = []
    for _, row in df.iterrows():
        stocks.append({
            "symbol": str(row["code"]),
            "name": str(row["name"]),
            "market": "CN",
        })
    return stocks


def refresh_stock_list() -> list[dict]:
    """拉取 A 股列表并缓存（东方财富优先，akshare 备用）"""
    stocks = []

    # 首选: 东方财富（HTTP，无 SSL 问题，分页并发）
    try:
        stocks = _fetch_from_eastmoney()
        logger.info(f"东方财富获取 A 股列表成功: {len(stocks)} 只")
    except Exception as e:
        logger.warning(f"东方财富获取失败: {e}")

        # 备用: akshare（带超时保护，防止 SSL 握手卡住）
        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(_fetch_from_akshare)
                stocks = future.result(timeout=15)
            logger.info(f"akshare 获取 A 股列表成功: {len(stocks)} 只")
        except concurrent.futures.TimeoutError:
            logger.error("akshare 获取超时（15s），可能是 SSL 问题")
        except Exception as e2:
            logger.error(f"所有数据源获取失败: {e2}")

    if stocks:
        _save_cache(stocks)
    return stocks


def get_stock_list() -> list[dict]:
    """获取股票列表(优先缓存)"""
    cached = _load_cache()
    if cached:
        return cached
    return refresh_stock_list()


def search_stocks(query: str, market: str = "", limit: int = 20) -> list[dict]:
    """模糊搜索股票，匹配代码前缀或名称包含"""
    stocks = get_stock_list()
    if not stocks:
        return []

    q = query.strip().upper()
    if not q:
        return []

    results = []
    for s in stocks:
        if market and s["market"] != market:
            continue
        code = s["symbol"].upper()
        name = s["name"].upper()
        # 代码前缀匹配优先
        if code.startswith(q):
            results.append((0, s))
        elif q in name:
            results.append((1, s))
        elif q in code:
            results.append((2, s))

        if len(results) >= limit * 2:
            break

    results.sort(key=lambda x: x[0])
    return [r[1] for r in results[:limit]]
