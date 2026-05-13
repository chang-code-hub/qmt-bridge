"""复权因子。

从 QMT (xtdata) 直接获取除权因子数据，存储累计复权系数。
用于前复权/后复权价格计算。
"""

from datetime import date, datetime

import pandas as pd
from xtquant import xtdata

from ..base import Factor, register


def _parse_date(dt) -> date:
    """将 xtdata 返回的时间戳转为 date 对象。"""
    if hasattr(dt, "item"):
        dt = dt.item()
    if isinstance(dt, (int, float)):
        dt = int(dt)
        if dt > 10 ** 10:
            return datetime.fromtimestamp(dt / 1000).date()
        s = str(dt)
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    if isinstance(dt, str):
        s = dt.strip()
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    if isinstance(dt, datetime):
        return dt.date()
    raise TypeError(f"无法解析日期: {dt!r}")


@register
class AdjustmentFactor(Factor):
    """复权因子。

    调用 ``xtdata.get_divid_factors()`` 获取除权除息明细数据，
    保存派息、送转股、配股等原始字段。

    输出字段：
        - ``interest``: 每股派息
        - ``stock_bonus``: 送股比例
        - ``stock_gift``: 转增股比例
        - ``allot_num``: 配股比例
        - ``allot_price``: 配股价格
        - ``gugai``: 股改
        - ``dr``: 除权日
    """

    name = "adjustment"
    description = "复权因子：基于 xtdata 除权因子计算的累计复权系数"

    @classmethod
    def required_period(cls) -> str:
        return "1d"

    @classmethod
    def required_bars(cls) -> int:
        return 1

    @classmethod
    def is_bulk_mode(cls) -> bool:
        return True

    @classmethod
    def db_columns(cls) -> list:
        from sqlalchemy import Column, Float

        return [
            Column("interest", Float),
            Column("stock_bonus", Float),
            Column("stock_gift", Float),
            Column("allot_num", Float),
            Column("allot_price", Float),
            Column("gugai", Float),
            Column("dr", Float),
        ]

    def compute(self, stock_code: str, bars_df: pd.DataFrame) -> list[dict]:
        # bars_df 的 index 是整数时间戳
        start_time = str(bars_df.index[0])[:8] if not bars_df.empty else ""
        end_time = str(bars_df.index[-1])[:8] if not bars_df.empty else ""

        raw = xtdata.get_divid_factors(stock_code, start_time=start_time, end_time=end_time)
        if raw is None:
            return []

        if isinstance(raw, pd.DataFrame):
            df = raw
        elif isinstance(raw, dict):
            if stock_code not in raw:
                return []
            df = raw[stock_code]
        else:
            return []

        if df is None or df.empty:
            return []

        records = []
        for _, row in df.iterrows():
            trade_date = _parse_date(row.get("time", 0))
            records.append(
                {
                    "trade_date": trade_date,
                    "factor_data": {
                        "interest": float(row.get("interest", 0.0)),
                        "stock_bonus": float(row.get("stockBonus", 0.0)),
                        "stock_gift": float(row.get("stockGift", 0.0)),
                        "allot_num": float(row.get("allotNum", 0.0)),
                        "allot_price": float(row.get("allotPrice", 0.0)),
                        "gugai": float(row.get("gugai", 0.0)),
                        "dr": float(row.get("dr", 0.0)),
                    },
                }
            )
        return records
