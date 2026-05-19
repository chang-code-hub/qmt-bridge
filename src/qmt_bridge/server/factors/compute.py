"""因子批量计算编排器。

负责从 xtdata 拉取 K 线、调用 Factor.compute()、并将结果写入 PostgreSQL。
"""

import logging
from datetime import date, datetime

import pandas as pd
from sqlalchemy.engine import Engine
from xtquant import xtdata

from ..helpers import normalize_stock_code
from .base import Factor, get_factor
from .db import upsert_factors
from ..downloader import download_history_data2_safe

logger = logging.getLogger("qmt_bridge")


def _parse_date(dt) -> date:
    """将 xtdata 返回的时间戳转为 date 对象。

    支持格式：
        - ``int/str`` 的 YYYYMMDD 格式，如 ``20250102``
        - ``int/float/np.int64/np.float64`` 的 Unix 毫秒时间戳，如 ``1348675200000.0``
        - ``datetime`` 对象
    """
    # numpy 标量 → Python 原生类型
    if hasattr(dt, "item"):
        dt = dt.item()

    if isinstance(dt, (int, float)):
        dt = int(dt)
        if dt > 10 ** 10:  # 毫秒时间戳（13位）
            return datetime.fromtimestamp(dt / 1000).date()
        if dt > 10 ** 7:  # YYYYMMDD 格式
            s = str(dt)
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        # 秒时间戳（10位）
        return datetime.fromtimestamp(dt).date()

    if isinstance(dt, str):
        s = dt.strip()
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))

    if isinstance(dt, datetime):
        return dt.date()

    raise TypeError(f"无法解析日期: {dt!r}")


def _ensure_kline_data(
    stock: str,
    period: str,
    start_time: str,
    end_time: str,
) -> pd.DataFrame | None:
    """获取单只股票K线数据，若最新日期不完整则自动下载补全。

    Returns:
        DataFrame 或 None（无数据时）。
    """
    raw = xtdata.get_market_data_ex(
        field_list=["time", "open", "high", "low", "close", "volume"],
        stock_list=[stock],
        period=period,
        start_time=start_time,
        end_time=end_time,
        count=-1,
        dividend_type="none",
    )
    df = raw.get(stock)

    if df is None or df.empty:
        return df

    from ..helpers import get_expected_last_trade_date
    expected_end = end_time or get_expected_last_trade_date()
    last_ts = df.index[-1]
    if isinstance(last_ts, pd.Timestamp):
        last_date = last_ts.strftime("%Y%m%d")
    else:
        last_date = last_ts[0:8]

    if last_date < expected_end:
        logger.info(
            "因子计算K线数据不完整，触发下载: %s %s", period, stock
        )
        download_history_data2_safe([stock], period=period, start_time=start_time, end_time=end_time)
        raw = xtdata.get_market_data_ex(
            field_list=["time", "open", "high", "low", "close", "volume"],
            stock_list=[stock],
            period=period,
            start_time=start_time,
            end_time=end_time,
            count=-1,
            dividend_type="none",
        )
        df = raw.get(stock)

    return df


def compute_factors_for_stocks(
    engine: Engine,
    factor: Factor,
    stock_codes: list[str],
    start_time: str = "",
    end_time: str = "",
) -> dict:
    """对一批股票批量计算指定因子并入库。

    K 线周期由因子自身的 ``required_period()`` 决定，无需外部传入。

    Args:
        engine: PostgreSQL Engine。
        factor: Factor 实例（已初始化）。
        stock_codes: 股票代码列表，如 ``["000001.SZ", "600519.SH"]``。
        start_time: 起始时间（YYYYMMDD），空字符串表示不限制。
        end_time: 结束时间（YYYYMMDD），空字符串表示不限制。

    Returns:
        统计信息 dict：``{"total": int, "success": int, "failed": int, "errors": list[str]}``。
    """
    period = factor.required_period()
    total = len(stock_codes)
    success = 0
    failed = 0
    errors = []

    logger.info(
        "因子计算开始: factor=%s, 股票=%d只, 周期=%s",
        factor.name,
        total,
        period,
    )

    for stock in stock_codes:
        stock = normalize_stock_code(stock)
        try:
            df = _ensure_kline_data(stock, period, start_time, end_time)
            actual_period = period

            # 主周期无数据，尝试回退周期
            if (df is None or df.empty) and factor.fallback_period():
                fallback = factor.fallback_period()
                df = _ensure_kline_data(stock, fallback, start_time, end_time)
                actual_period = fallback

            if df is None or df.empty:
                logger.warning("因子计算跳过: %s 无数据", stock)
                continue

            # 按日期粒度计算因子（逐日滚动窗口）
            records = _compute_daily(engine, factor, stock, df, actual_period)
            if records:
                upsert_factors(engine, factor.name, records)
                success += 1
            else:
                logger.warning("因子计算无结果: %s", stock)

        except Exception:
            logger.exception("因子计算失败: %s", stock)
            failed += 1
            errors.append(stock)

    logger.info(
        "因子计算完成: factor=%s, 成功=%d, 失败=%d",
        factor.name,
        success,
        failed,
    )
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "errors": errors,
    }


def _compute_daily(
    engine: Engine,
    factor: Factor,
    stock_code: str,
    df: pd.DataFrame,
    period: str | None = None,
) -> list[dict]:
    """对单只股票的 DataFrame 计算因子。

    支持三种模式：
    - bulk 模式（全量一次性）：因子 ``is_bulk_mode=True``，``compute()`` 返回 ``list[dict]``
    - 分钟线：按交易日分组，每天独立计算
    - 日线：滚动窗口计算
    """
    if period is None:
        period = factor.required_period()

    # bulk 模式：一次性全量计算
    if factor.is_bulk_mode():
        result = factor.compute(stock_code, df)
        if isinstance(result, list):
            return [
                {
                    "stock_code": stock_code,
                    "trade_date": rec["trade_date"],
                    "factor_name": factor.name,
                    "factor_data": rec["factor_data"],
                }
                for rec in result
            ]
        return []

    # 确定实际需要的 bars 数
    if period == factor.fallback_period() and factor.fallback_bars() is not None:
        required_bars = factor.fallback_bars()
    else:
        required_bars = factor.required_bars()

    # 分钟线：按交易日分组，每天取当天的全部 K 线计算
    if period in ("1m", "5m", "15m", "30m"):
        df = df.copy()
        df["_trade_date"] = df["time"].apply(_parse_date)
        records = []
        for trade_date, day_df in df.groupby("_trade_date"):
            day_df = day_df.drop(columns=["_trade_date"])
            if len(day_df) < required_bars:
                logger.warning(
                    "数据不足: %s %s 只有 %d 条，需要 %d 条",
                    stock_code,
                    trade_date,
                    len(day_df),
                    required_bars,
                )
                continue
            factor_data = factor.compute(stock_code, day_df)
            if factor_data:
                records.append(
                    {
                        "stock_code": stock_code,
                        "trade_date": trade_date,
                        "factor_name": factor.name,
                        "factor_data": factor_data,
                    }
                )
        return records

    # 日线：滚动窗口计算
    if len(df) < required_bars:
        logger.warning(
            "数据不足: %s 只有 %d 条，需要 %d 条",
            stock_code,
            len(df),
            required_bars,
        )
        return []

    records = []
    for i in range(required_bars - 1, len(df)):
        window = df.iloc[i - required_bars + 1 : i + 1].copy()
        trade_date = _parse_date(window.iloc[-1]["time"])
        factor_data = factor.compute(stock_code, window)
        if factor_data:
            records.append(
                {
                    "stock_code": stock_code,
                    "trade_date": trade_date,
                    "factor_name": factor.name,
                    "factor_data": factor_data,
                }
            )
    return records


def compute_all_registered_factors(
    engine: Engine,
    stock_codes: list[str],
    factor_names: list[str] | None = None,
    start_time: str = "",
    end_time: str = "",
) -> dict:
    """计算指定因子。

    每个因子使用各自的 ``required_period()`` 拉取对应周期的 K 线数据。

    Args:
        engine: PostgreSQL Engine。
        stock_codes: 股票代码列表。
        factor_names: 要计算的因子名称列表，为 ``None`` 时计算全部已注册因子。
        start_time: 起始时间（YYYYMMDD），空字符串表示不限制。
        end_time: 结束时间（YYYYMMDD），空字符串表示不限制。

    Returns:
        各因子的统计信息 dict，键为因子名。
    """
    from .base import list_factors

    # 若指定了 factor_names，则只计算这些因子
    if factor_names:
        allowed = set(factor_names)
        targets = [m for m in list_factors() if m["name"] in allowed]
    else:
        targets = list_factors()

    results = {}
    for meta in targets:
        factor_cls = get_factor(meta["name"])
        if factor_cls is None:
            continue
        factor = factor_cls()
        results[factor.name] = compute_factors_for_stocks(
            engine, factor, stock_codes, start_time=start_time, end_time=end_time
        )
    return results
