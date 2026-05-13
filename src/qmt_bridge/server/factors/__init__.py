"""自定义因子计算与持久化包。

提供因子注册表、数据库模型、计算编排和内置因子实现。
"""

from .base import Factor, get_factor, list_factors, register
from .impl import AdjustmentFactor, ChipDistributionFactor
from .compute import compute_all_registered_factors, compute_factors_for_stocks
from .db import create_tables, make_engine, query_factors, upsert_factors

__all__ = [
    "Factor",
    "register",
    "get_factor",
    "list_factors",
    "ChipDistributionFactor",
    "AdjustmentFactor",
    "make_engine",
    "create_tables",
    "upsert_factors",
    "query_factors",
    "compute_factors_for_stocks",
    "compute_all_registered_factors",
]
