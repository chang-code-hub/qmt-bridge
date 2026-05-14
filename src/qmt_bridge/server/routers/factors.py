"""因子查询与计算路由。

查询端点（list / get）不依赖 xtdata，独立注册不加锁。
计算端点（compute）调用 xtdata 获取 K 线，需串行化锁。
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import Settings, get_settings
from ..factors import compute_factors_for_stocks, get_factor, list_factors, make_engine, query_factors
from ..helpers import ok_response
from ..models import FactorComputeRequest

logger = logging.getLogger("qmt_bridge")

# ---------------------------------------------------------------------------
# 查询路由（无需 xtdata 锁）
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/factors", tags=["factors"])


def _get_db_engine(settings: Settings = Depends(get_settings)):
    """获取或创建 DB Engine。"""
    return make_engine(settings)


@router.get("/list")
def list_all_factors():
    """列出所有已注册的因子。"""
    return ok_response(list_factors())


_VALID_DIVIDEND_TYPES = {"none", "front", "back", "front_ratio", "back_ratio"}


def _build_adj_map(adj_records: list[dict]) -> dict[str, float]:
    """从除权除息原始字段计算日期 -> cum_factor 映射。

    基于送转股比例（stock_bonus + stock_gift）计算等比累计复权系数：
        cum_factor *= (1 + stock_bonus + stock_gift)
    相邻日期送转股比例相同时视为同一事件，不重复计算。
    """
    if not adj_records:
        return {}

    sorted_records = sorted(adj_records, key=lambda r: r["trade_date"])
    adj_map: dict[str, float] = {}
    cum_factor = 1.0
    prev_ratio = (0.0, 0.0)

    for r in sorted_records:
        data = r["factor_data"]
        bonus = float(data.get("stock_bonus") or 0.0)
        gift = float(data.get("stock_gift") or 0.0)
        current = (bonus, gift)

        # 送转股比例变化 → 新除权事件
        if current != prev_ratio and (bonus > 0 or gift > 0):
            cum_factor *= (1.0 + bonus + gift)
            prev_ratio = current

        adj_map[r["trade_date"]] = cum_factor

    return adj_map


def _adjust_value(value, ratio: float):
    """用复权比例调整单个值（支持标量和列表）。"""
    if isinstance(value, list):
        return [v * ratio for v in value]
    if isinstance(value, (int, float)):
        return value * ratio
    return value


def _apply_adjustment(
    results: list[dict],
    adj_map: dict[str, float],
    price_fields: list[str],
    dividend_type: str,
):
    """对查询结果应用复权调整（原地修改）。

    复权类型：
        - front / front_ratio: 前复权（以最新价格为基准）
        - back / back_ratio: 后复权（以最早价格为基准）
    """
    if not adj_map or not price_fields:
        return

    dates = sorted(adj_map.keys())
    latest_cum = adj_map[dates[-1]]
    earliest_cum = adj_map[dates[0]]

    for r in results:
        date_key = r["trade_date"]
        date_cum = adj_map.get(date_key, 1.0)
        if not date_cum:
            continue

        # 前复权: price * (latest_cum / date_cum)
        # 后复权: price * (date_cum / earliest_cum)
        if dividend_type in ("front", "front_ratio"):
            ratio = latest_cum / date_cum
        else:
            ratio = date_cum / earliest_cum

        for field in price_fields:
            if field in r["factor_data"]:
                r["factor_data"][field] = _adjust_value(
                    r["factor_data"][field], ratio
                )


@router.get("/{factor_name}")
def get_factor_history(
    factor_name: str,
    stocks : str = Query(..., description="股票代码列表，逗号分隔"),
    start_date: str = Query("", description="开始时间"),
    end_date: str = Query("", description="结束时间"),
    dividend_type: str = Query(
        "none",
        description="除权类型: none(不复权)/front(前复权)/back(后复权)/front_ratio(等比前复权)/back_ratio(等比后复权)",
    ),
    engine=Depends(_get_db_engine),
):
    """查询指定股票、指定因子的历史数据。

    支持前复权/后复权调整（仅当因子声明了 price_fields 时生效）。
    等比复权基于送转股比例计算；非等比复权因缺少收盘价信息，实际结果与等比复权一致。
    """
    if dividend_type not in _VALID_DIVIDEND_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 dividend_type: {dividend_type}，可选值: {_VALID_DIVIDEND_TYPES}"
        )

    factor_cls = get_factor(factor_name)
    if factor_cls is None:
        raise HTTPException(status_code=404, detail=f"未知因子: {factor_name}")

    stock_codes = [s.strip() for s in stocks.split(",")]
    results = query_factors(engine, factor_name, stock_codes, start_date, end_date)

    # 检查缺失或日期范围不完整的股票并触发补充计算
    from collections import defaultdict

    stock_dates: defaultdict[str, list[str]] = defaultdict(list)
    for r in results:
        stock_dates[r["stock_code"]].append(r["trade_date"])

    missing_stocks: list[str] = []
    for stock_code in stock_codes:
        dates = sorted(stock_dates.get(stock_code, []))
        if not dates:
            missing_stocks.append(stock_code)
            continue
        # 最早记录晚于 start_date → 前面有缺失
        if start_date and dates[0] > start_date:
            missing_stocks.append(stock_code)
        # 最晚记录早于 end_date → 后面有缺失
        elif end_date and dates[-1] < end_date:
            missing_stocks.append(stock_code)

    if missing_stocks:
        logger.info(
            "因子数据缺失，触发补充计算: factor=%s, 股票=%s",
            factor_name,
            missing_stocks,
        )
        factor = factor_cls()
        compute_factors_for_stocks(
            engine, factor, missing_stocks, start_time=start_date, end_time=end_date
        )
        results = query_factors(engine, factor_name, stock_codes, start_date, end_date)

    # 复权调整
    if dividend_type != "none":
        price_fields = factor_cls.price_fields()
        if price_fields:
            adj_records = query_factors(engine, "adjustment", stock_codes, "", "")
            adj_map = _build_adj_map(adj_records)
            _apply_adjustment(results, adj_map, price_fields, dividend_type)

    return ok_response(results)


# ---------------------------------------------------------------------------
# 计算路由（需 xtdata 锁，独立注册）
# ---------------------------------------------------------------------------

compute_router = APIRouter(prefix="/api/factors", tags=["factors"])


def _resolve_start_time(start_time: str, years: int) -> str:
    """根据传入的 start_time 或 years 计算最终起始时间（YYYYMMDD）。"""
    if years > 0:
        dt = datetime.now() - timedelta(days=years * 365)
        return dt.strftime("%Y%m%d")
    return start_time


@compute_router.post("/compute")
def compute_factor(
    request: FactorComputeRequest,
    settings: Settings = Depends(get_settings),
):
    """手动触发指定因子对指定股票的计算。

    此端点会调用 xtdata 获取 K 线并执行因子计算，结果写入 PostgreSQL。
    """
    factor_cls = get_factor(request.factor_name)
    if factor_cls is None:
        raise HTTPException(status_code=404, detail=f"未知因子: {request.factor_name}")

    if not request.stock_codes:
        raise HTTPException(status_code=400, detail="stock_codes 不能为空")

    factor = factor_cls()
    engine = make_engine(settings)
    start_time = _resolve_start_time(request.start_time, request.years)

    logger.info(
        "手动触发因子计算: factor=%s, 股票=%s, 周期=%s, 起始=%s, 结束=%s",
        request.factor_name,
        request.stock_codes,
        factor.required_period(),
        start_time or "不限",
        request.end_time or "不限",
    )

    result = compute_factors_for_stocks(
        engine,
        factor,
        request.stock_codes,
        start_time=start_time,
        end_time=request.end_time,
    )
    return ok_response(result)
