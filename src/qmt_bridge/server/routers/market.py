"""行情数据路由模块 /api/market/*。

提供股票/指数的实时快照、K线历史行情、除权因子、逐笔委托簿等端点。
底层调用 xtquant.xtdata 的行情数据接口，包括：
- xtdata.get_full_tick()          — 获取全推行情快照
- xtdata.get_market_data_ex()     — 获取扩展行情数据（返回 DataFrame 字典）
- xtdata.get_local_data()         — 获取本地缓存行情数据
- xtdata.get_divid_factors()      — 获取除权因子
- xtdata.get_market_data()        — 获取行情数据（原始 API）
- xtdata.get_market_data3()       — 获取行情数据 v3
- xtdata.get_full_kline()         — 获取完整 K 线
- xtdata.get_fullspeed_orderbook()— 获取极速委托簿
- xtdata.get_transactioncount()   — 获取逐笔成交计数
"""

import logging
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Query
from xtquant import xtdata

from ..downloader import download_history_data2_safe
from ..helpers import _dataframe_dict_to_records, _numpy_to_python, get_expected_last_trade_date

from ..helpers import _market_data_to_records

router = APIRouter(prefix="/api/market", tags=["market"])
logger = logging.getLogger("qmt_bridge")

# 主要指数列表（用于 /indices 端点快速查询大盘行情）
MAJOR_INDICES = [
    "000001.SH",  # 上证指数
    "399001.SZ",  # 深证成指
    "399006.SZ",  # 创业板指
    "000300.SH",  # 沪深300
    "000016.SH",  # 上证50
    "000905.SH",  # 中证500
    "000852.SH",  # 中证1000
]


# ── 自动同步辅助函数 ──────────────────────────────────────────

def _get_latest_date_from_df(df) -> str:
    """从 DataFrame 索引提取最新日期字符串（YYYYMMDD）。"""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return ""
    last_ts = df.index[-1]
    if isinstance(last_ts, (int, float)):
        dt = datetime.fromtimestamp(last_ts / 1000)
    else:
        dt = pd.Timestamp(last_ts).to_pydatetime()
    return dt.strftime("%Y%m%d")


def _get_latest_date_from_market_data(raw: dict, stock: str) -> str:
    """从 get_market_data 返回的 {field: DataFrame} 中提取某只股票的最新日期。"""
    latest = ""
    for field_df in raw.values():
        if not isinstance(field_df, pd.DataFrame) or stock not in field_df.index:
            continue
        if len(field_df.columns) == 0:
            continue
        last_ts = field_df.columns[-1]
        if isinstance(last_ts, (int, float)):
            dt = datetime.fromtimestamp(last_ts / 1000)
        else:
            dt = pd.Timestamp(last_ts).to_pydatetime()
        date_str = dt.strftime("%Y%m%d")
        if date_str > latest:
            latest = date_str
    return latest


def _is_market_data_format(raw: dict, stock_list: list[str]) -> bool:
    """判断 raw 是否为 get_market_data 返回的 {field: DataFrame} 格式。

    与 {stock: DataFrame} 的区别：前者 DataFrame 的 index 是字段名/时间，
    后者 index 是股票代码。
    """
    if not raw:
        return False
    first_val = next(iter(raw.values()))
    if not isinstance(first_val, pd.DataFrame) or first_val.empty:
        return False
    # 若第一个 index 在 stock_list 中，则是 {stock: DataFrame} 格式
    return str(first_val.index[0]) not in stock_list


def _check_and_sync_data(
    raw: dict,
    stock_list: list[str],
    period: str,
    end_time: str = "",
    query_fn=None,
    **query_kwargs,
) -> dict:
    """检查数据完整性，缺失时自动下载并重新获取。

    Args:
        raw: xtdata 返回数据。支持两种格式：
            - {stock_code: DataFrame}（get_market_data_ex / get_local_data）
            - {field: DataFrame}（get_market_data，DataFrame index 为股票代码）
        stock_list: 查询的股票代码列表。
        period: K 线周期。
        end_time: 用户传入的结束时间，为空表示查询到最新。
        query_fn: 自定义重新查询函数，为 None 时默认使用 ``xtdata.get_local_data``。
        **query_kwargs: 重新查询时传给 ``xtdata.get_local_data`` 的额外参数
            （如 start_time、count、dividend_type、fill_data 等）。

    Returns:
        补全后的 raw 字典。
    """
    expected_end = get_expected_last_trade_date()

    # 若用户指定了结束时间且早于预期最后交易日，不触发自动同步
    if end_time and end_time < expected_end:
        return raw

    is_md_fmt = _is_market_data_format(raw, stock_list)

    missing_stocks: list[str] = []
    for stock in stock_list:
        if is_md_fmt:
            latest_date = _get_latest_date_from_market_data(raw, stock)
        else:
            df = raw.get(stock)
            latest_date = _get_latest_date_from_df(df)
        if not latest_date or latest_date < expected_end:
            missing_stocks.append(stock)

    if missing_stocks:
        logger.info(
            "行情数据不完整，触发下载: period=%s, expected=%s, 股票=%s",
            period,
            expected_end,
            missing_stocks,
        )
        download_history_data2_safe(missing_stocks, period=period)
        if query_fn is not None:
            raw = query_fn()
        else:
            # 重新从本地读取补全后的数据，保留原始查询参数
            raw = xtdata.get_local_data(
                field_list=[],
                stock_list=stock_list,
                period=period,
                **query_kwargs,
            )

    return raw


@router.get("/full_tick")
def get_full_tick(
    stocks: str = Query(..., description="股票/指数代码列表，逗号分隔，如 000001.SH,000001.SZ"),
):
    """获取实时全推行情快照。

    Args:
        stocks: 逗号分隔的股票/指数代码，如 "000001.SH,000001.SZ"。

    Returns:
        各代码对应的全推行情数据字典。

    底层调用: xtdata.get_full_tick(code_list=...)
    """
    # 将逗号分隔的代码字符串拆分为列表
    stock_list = [s.strip() for s in stocks.split(",")]
    raw = xtdata.get_full_tick(code_list=stock_list)
    return {"data": _numpy_to_python(raw)}


@router.get("/indices")
def get_major_indices():
    """获取主要指数的实时行情快照。

    返回预定义的主要指数（上证指数、深证成指、创业板指、沪深300 等）的全推行情。

    Returns:
        indices: 指数代码列表。
        data: 各指数的全推行情数据。

    底层调用: xtdata.get_full_tick(code_list=MAJOR_INDICES)
    """
    raw = xtdata.get_full_tick(code_list=MAJOR_INDICES)
    return {"indices": MAJOR_INDICES, "data": _numpy_to_python(raw)}


@router.get("/market_data_ex")
def get_market_data_ex(
    stocks: str = Query(..., description="股票代码列表，逗号分隔，如 000001.SZ,600519.SH"),
    period: str = Query("1d", description="K线周期: tick/1m/5m/15m/30m/60m/1d"),
    start_time: str = Query("", description="开始时间 YYYYMMDD 或 YYYYMMDDHHmmss"),
    end_time: str = Query("", description="结束时间"),
    count: int = Query(-1, description="返回条数，-1 表示不限"),
    dividend_type: str = Query("none", description="除权类型: none/front/back/front_ratio/back_ratio"),
    fill_data: bool = Query(True, description="是否填充空数据"),
):
    """获取扩展 K 线历史行情数据。

    Args:
        stocks: 逗号分隔的股票代码列表。
        period: K 线周期，支持 tick/1m/5m/15m/30m/60m/1d。
        start_time: 开始时间，格式 YYYYMMDD 或 YYYYMMDDHHmmss。
        end_time: 结束时间。
        count: 返回数据条数，-1 表示全部。
        dividend_type: 除权类型（none/front/back/front_ratio/back_ratio）。
        fill_data: 是否对非交易时段进行数据填充。

    Returns:
        按股票代码分组的 K 线记录列表。

    底层调用: xtdata.get_market_data_ex(field_list=[], stock_list=..., ...)
    """
    stock_list = [s.strip() for s in stocks.split(",")]
    raw = xtdata.get_market_data_ex(
        field_list=[],
        stock_list=stock_list,
        period=period,
        start_time=start_time,
        end_time=end_time,
        count=count,
        dividend_type=dividend_type,
        fill_data=fill_data,
    )
    raw = _check_and_sync_data(
        raw, stock_list, period,
        start_time=start_time, end_time=end_time, count=count,
        dividend_type=dividend_type, fill_data=fill_data,
    )
    return {"data": _dataframe_dict_to_records(raw)}


@router.get("/local_data")
def get_local_data(
    stocks: str = Query(..., description="股票代码列表，逗号分隔"),
    period: str = Query("1d", description="K线周期"),
    start_time: str = Query("", description="开始时间"),
    end_time: str = Query("", description="结束时间"),
    count: int = Query(-1, description="返回条数"),
    dividend_type: str = Query("none", description="除权类型"),
    fill_data: bool = Query(True, description="是否填充空数据"),
):
    """获取本地缓存的行情数据（不触发网络请求）。

    与 history_ex 的区别在于只读取已下载到本地的数据，不会向服务器请求缺失数据。

    Args:
        stocks: 逗号分隔的股票代码列表。
        period: K 线周期。
        start_time: 开始时间。
        end_time: 结束时间。
        count: 返回数据条数。
        dividend_type: 除权类型。
        fill_data: 是否填充空数据。

    Returns:
        按股票代码分组的本地 K 线记录列表。

    底层调用: xtdata.get_local_data(field_list=[], stock_list=..., ...)
    """
    stock_list = [s.strip() for s in stocks.split(",")]
    raw = xtdata.get_local_data(
        field_list=[],
        stock_list=stock_list,
        period=period,
        start_time=start_time,
        end_time=end_time,
        count=count,
        dividend_type=dividend_type,
        fill_data=fill_data,
    )
    raw = _check_and_sync_data(
        raw, stock_list, period,
        start_time=start_time, end_time=end_time, count=count,
        dividend_type=dividend_type, fill_data=fill_data,
    )
    return {"data": _dataframe_dict_to_records(raw)}


@router.get("/divid_factors")
def get_divid_factors(
    stock: str = Query(..., description="股票代码，如 000001.SZ"),
    start_time: str = Query("", description="开始时间"),
    end_time: str = Query("", description="结束时间"),
):
    """获取指定股票的除权因子数据。

    除权因子用于将历史价格进行前/后复权计算。

    Args:
        stock: 单个股票代码。
        start_time: 开始时间。
        end_time: 结束时间。

    Returns:
        该股票在指定时间范围内的除权因子数据。

    底层调用: xtdata.get_divid_factors(stock, start_time=..., end_time=...)
    """
    raw = xtdata.get_divid_factors(stock, start_time=start_time, end_time=end_time)

    # 自动同步：若数据为空，尝试下载该股票日线后重新获取
    if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty):
        logger.info("除权因子数据为空，尝试同步: %s", stock)
        try:
            xtdata.download_history_data(stock, period="1d")
        except Exception as exc:
            logger.warning("除权因子同步下载失败 %s: %s", stock, exc)
        raw = xtdata.get_divid_factors(stock, start_time=start_time, end_time=end_time)

    return {"stock": stock, "data": _numpy_to_python(raw)}


# ---------------------------------------------------------------------------
# 以下为扩展行情端点
# ---------------------------------------------------------------------------


@router.get("/market_data")
def get_market_data(
    stocks: str = Query(..., description="股票代码列表，逗号分隔"),
    fields: str = Query("open,high,low,close,volume", description="字段列表，逗号分隔"),
    period: str = Query("1d", description="K线周期"),
    start_time: str = Query("", description="开始时间"),
    end_time: str = Query("", description="结束时间"),
    count: int = Query(-1, description="返回条数"),
    dividend_type: str = Query("none", description="除权类型"),
    fill_data: bool = Query(True, description="是否填充空数据"),
):
    """通过原始 get_market_data 接口获取行情数据。

    返回格式为 {字段: {股票: numpy 数组}} 的嵌套结构，
    经转换后以记录列表的形式返回。

    Args:
        stocks: 逗号分隔的股票代码列表。
        fields: 逗号分隔的字段列表（如 open,high,low,close,volume）。
        period: K 线周期。
        start_time: 开始时间。
        end_time: 结束时间。
        count: 返回条数。
        dividend_type: 除权类型。
        fill_data: 是否填充空数据。

    Returns:
        按股票代码分组的行情记录列表。

    底层调用: xtdata.get_market_data(field_list=..., stock_list=..., ...)
    """

    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]
    raw = xtdata.get_market_data(
        field_list=field_list,
        stock_list=stock_list,
        period=period,
        start_time=start_time,
        end_time=end_time,
        count=count,
        dividend_type=dividend_type,
        fill_data=fill_data,
    )
    raw = _check_and_sync_data(
        raw, stock_list, period, end_time,
        query_fn=lambda: xtdata.get_market_data(
            field_list=field_list,
            stock_list=stock_list,
            period=period,
            start_time=start_time,
            end_time=end_time,
            count=count,
            dividend_type=dividend_type,
            fill_data=fill_data,
        ),
    )
    records = _market_data_to_records(raw, stock_list, field_list)
    return {"data": records}


@router.get("/market_data3")
def get_market_data3(
    stocks: str = Query(..., description="股票代码列表，逗号分隔"),
    fields: str = Query("", description="字段列表，逗号分隔，为空取全部"),
    period: str = Query("1d", description="K线周期"),
    start_time: str = Query("", description="开始时间"),
    end_time: str = Query("", description="结束时间"),
    count: int = Query(-1, description="返回条数"),
    dividend_type: str = Query("none", description="除权类型"),
    fill_data: bool = Query(True, description="是否填充空数据"),
):
    """通过 get_market_data3 接口获取行情数据（返回 DataFrame 字典）。

    与 market_data 的区别在于返回格式不同，此版本直接返回
    {股票代码: DataFrame} 字典，更便于处理多只股票的数据。

    Args:
        stocks: 逗号分隔的股票代码列表。
        fields: 逗号分隔的字段列表，为空则获取全部字段。
        period: K 线周期。
        start_time: 开始时间。
        end_time: 结束时间。
        count: 返回条数。
        dividend_type: 除权类型。
        fill_data: 是否填充空数据。

    Returns:
        按股票代码分组的行情记录列表。

    底层调用: xtdata.get_market_data3(field_list=..., stock_list=..., ...)
    """
    stock_list = [s.strip() for s in stocks.split(",")]
    # 字段为空字符串时传入空列表，表示获取全部字段
    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else []
    raw = xtdata.get_market_data3(
        field_list=field_list,
        stock_list=stock_list,
        period=period,
        start_time=start_time,
        end_time=end_time,
        count=count,
        dividend_type=dividend_type,
        fill_data=fill_data,
    )
    raw = _check_and_sync_data(
        raw, stock_list, period,
        start_time=start_time, end_time=end_time, count=count,
        dividend_type=dividend_type, fill_data=fill_data,
    )
    return {"data": _dataframe_dict_to_records(raw)}


@router.get("/full_kline")
def get_full_kline(
    stock: str = Query(..., description="股票代码"),
    period: str = Query("1d", description="K线周期"),
    start_time: str = Query("", description="开始时间"),
    end_time: str = Query("", description="结束时间"),
):
    """获取单只股票的完整 K 线数据。

    Args:
        stock: 单个股票代码。
        period: K 线周期。
        start_time: 开始时间。
        end_time: 结束时间。

    Returns:
        该股票的完整 K 线数据。

    底层调用: xtdata.get_full_kline(stock, period=..., ...)
    """
    raw = xtdata.get_full_kline(stock, period=period, start_time=start_time, end_time=end_time)
    # full_kline 返回单只股票的 DataFrame，包装为 dict 以复用自动同步逻辑
    raw_wrapper = {stock: raw} if isinstance(raw, pd.DataFrame) else {}
    raw_wrapper = _check_and_sync_data(
        raw_wrapper, [stock], period,
        start_time=start_time, end_time=end_time,
    )
    raw = raw_wrapper.get(stock)
    return {"stock": stock, "data": _numpy_to_python(raw)}


@router.get("/fullspeed_orderbook")
def get_fullspeed_orderbook(
    stock: str = Query(..., description="股票代码"),
    start_time: str = Query("", description="开始时间"),
    end_time: str = Query("", description="结束时间"),
):
    """获取极速委托簿数据。

    提供逐笔级别的委托簿快照数据，适用于高频策略分析。

    Args:
        stock: 单个股票代码。
        start_time: 开始时间。
        end_time: 结束时间。

    Returns:
        该股票的极速委托簿数据。

    底层调用: xtdata.get_fullspeed_orderbook(stock, start_time=..., end_time=...)
    """
    raw = xtdata.get_fullspeed_orderbook(stock, start_time=start_time, end_time=end_time)
    return {"stock": stock, "data": _numpy_to_python(raw)}


@router.get("/transactioncount")
def get_transactioncount(
    stock: str = Query(..., description="股票代码"),
    start_time: str = Query("", description="开始时间"),
    end_time: str = Query("", description="结束时间"),
):
    """获取逐笔成交计数数据。

    Args:
        stock: 单个股票代码。
        start_time: 开始时间。
        end_time: 结束时间。

    Returns:
        该股票的逐笔成交计数数据。

    底层调用: xtdata.get_transactioncount(stock, start_time=..., end_time=...)
    """
    raw = xtdata.get_transactioncount(stock, start_time=start_time, end_time=end_time)
    return {"stock": stock, "data": _numpy_to_python(raw)}
