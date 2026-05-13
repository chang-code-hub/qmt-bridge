"""筹码分布因子。

将历史 K 线的成交量按价格区间分布，估算不同价格位的持仓成本分布。
常用于判断支撑/压力位、平均成本、获利盘比例等。
"""

import numpy as np
import pandas as pd

from ..base import Factor, register


@register
class ChipDistributionFactor(Factor):
    """筹码分布因子。

    算法说明：
    1. 遍历每根 K 线，将该 bar 的成交量均匀分布到 ``[low, high]`` 价格区间（每根 bar 内分 10 档）。
    2. 对所有 bar 的价格-成交量点做全局加权直方图（默认 50 档）。
    3. 计算平均成本、最大筹码价格、90% 集中度等统计量。

    输出字段：
        - ``price_levels``: 各档位价格中心
        - ``volumes``: 各档位筹码量
        - ``avg_cost``: 加权平均成本
        - ``max_volume_price``: 筹码峰值对应价格
        - ``concentration``: 90% 筹码集中度（(P95-P05)/avg_cost）
        - ``total_volume``: 总成交量
    """

    name = "chip"
    description = "筹码分布：基于历史 K 线成交量估算各价格位的持仓成本分布"

    INTRA_BAR_BINS = 10   # 单根 K 线内部分档数
    GLOBAL_BINS = 50      # 全局直方图分档数

    @classmethod
    def required_period(cls) -> str:
        return "1m"

    @classmethod
    def required_bars(cls) -> int:
        # A 股每天约 240 根 1min K 线，取半天作为最低门槛
        return 120

    @classmethod
    def db_columns(cls) -> list:
        from sqlalchemy import ARRAY, Column, Float

        return [
            Column("price_levels", ARRAY(Float)),
            Column("volumes", ARRAY(Float)),
            Column("avg_cost", Float),
            Column("max_volume_price", Float),
            Column("concentration", Float),
            Column("total_volume", Float),
        ]

    @classmethod
    def price_fields(cls) -> list[str]:
        return ["price_levels", "avg_cost", "max_volume_price"]

    def compute(self, stock_code: str, bars_df: pd.DataFrame) -> dict:
        if bars_df.empty:
            return {}

        required = {"low", "high", "volume"}
        if not required.issubset(bars_df.columns):
            missing = required - set(bars_df.columns)
            raise ValueError(f"缺少必要列: {missing}")

        all_prices = []
        all_volumes = []

        for _, row in bars_df.iterrows():
            low = float(row["low"])
            high = float(row["high"])
            vol = float(row["volume"])
            if vol > 0 and high > low:
                prices = np.linspace(low, high, self.INTRA_BAR_BINS)
                vol_per = vol / self.INTRA_BAR_BINS
                all_prices.extend(prices)
                all_volumes.extend([vol_per] * self.INTRA_BAR_BINS)

        if not all_volumes:
            return {}

        price_min = min(all_prices)
        price_max = max(all_prices)
        if price_max == price_min:
            return {}

        hist, edges = np.histogram(
            all_prices,
            bins=self.GLOBAL_BINS,
            weights=all_volumes,
            range=(price_min, price_max),
        )
        price_levels = edges[:-1].tolist()
        volumes = hist.tolist()
        total_volume = sum(all_volumes)

        # 平均成本
        weighted_sum = sum(p * v for p, v in zip(price_levels, volumes))
        avg_cost = weighted_sum / total_volume if total_volume > 0 else 0.0

        # 最大筹码价格
        max_idx = int(np.argmax(hist)) if len(hist) > 0 else 0
        max_volume_price = price_levels[max_idx] if max_idx < len(price_levels) else 0.0

        # 90% 集中度
        cumsum = np.cumsum(volumes)
        cumsum_norm = cumsum / cumsum[-1] if cumsum[-1] > 0 else cumsum
        idx_05 = int(np.searchsorted(cumsum_norm, 0.05))
        idx_95 = int(np.searchsorted(cumsum_norm, 0.95))
        price_05 = float(edges[idx_05]) if idx_05 < len(edges) else price_min
        price_95 = float(edges[idx_95]) if idx_95 < len(edges) else price_max
        concentration = (price_95 - price_05) / avg_cost if avg_cost > 0 else 0.0

        return {
            "price_levels": price_levels,
            "volumes": volumes,
            "avg_cost": float(avg_cost),
            "max_volume_price": float(max_volume_price),
            "concentration": float(concentration),
            "total_volume": float(total_volume),
        }
