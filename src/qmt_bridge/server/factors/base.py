"""因子抽象基类与注册表。

新增因子只需：
1. 继承 ``Factor``
2. 实现 ``compute()``
3. 添加 ``@register`` 装饰器

示例::

    @register
    class MyFactor(Factor):
        name = "my_factor"
        description = "我的自定义因子"

        def compute(self, stock_code, bars_df):
            return {"value": bars_df["close"].mean()}
"""

from abc import ABC, abstractmethod

import pandas as pd


class Factor(ABC):
    """因子抽象基类。

    子类必须设置 ``name``、``description``，并实现 ``compute()``。
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def compute(self, stock_code: str, bars_df: pd.DataFrame) -> dict:
        """根据 K 线数据计算因子值。

        Args:
            stock_code: 股票代码，如 ``"000001.SZ"``。
            bars_df: K 线 DataFrame，至少包含
                ``time`` / ``open`` / ``high`` / ``low`` / ``close`` / ``volume`` 列。

        Returns:
            可 JSON 序列化的 dict，将被写入 PostgreSQL JSONB 字段。
        """
        ...

    @classmethod
    def required_period(cls) -> str:
        """计算所需的最小 K 线周期。"""
        return "1d"

    @classmethod
    def required_bars(cls) -> int:
        """计算所需的最少 K 线条数。"""
        return 60

    @classmethod
    def db_columns(cls) -> list:
        """返回该因子数据表的列定义（SQLAlchemy Column 对象列表）。

        子类**必须覆盖**此方法，将 ``compute()`` 返回的 dict 中的每个键
        声明为独立的表列。框架会自动添加 ``stock_code``、``trade_date``、
        ``updated_at`` 三列，不需要在此处声明。

        示例::

            from sqlalchemy import Column, Float, ARRAY

            @classmethod
            def db_columns(cls) -> list:
                return [
                    Column("avg_cost", Float),
                    Column("concentration", Float),
                ]
        """
        return []

    @classmethod
    def price_fields(cls) -> list[str]:
        """返回需要复权调整的价格字段名列表。

        子类若包含价格类字段（如均价、价格档位等），应覆盖此方法声明，
        供查询接口做前/后复权调整。
        """
        return []

    @classmethod
    def fallback_period(cls) -> str | None:
        """当 ``required_period()`` 数据不可用时回退到的 K 线周期。

        返回 ``None`` 表示不回退。
        """
        return None

    @classmethod
    def fallback_bars(cls) -> int | None:
        """回退周期下所需的最少 K 线条数。

        返回 ``None`` 表示回退时使用 ``required_bars()`` 的值。
        """
        return None

    @classmethod
    def is_bulk_mode(cls) -> bool:
        """是否为全量计算模式。

        - ``False``（默认）：按天滚动计算，``compute()`` 接收当天/窗口数据，返回单条 ``dict``。
        - ``True``：一次性全量计算，``compute()`` 接收全部历史数据，返回 ``list[dict]``，
          每条含 ``trade_date`` 和 ``factor_data``。
        """
        return False


# ---------------------------------------------------------------------------
# 全局注册表
# ---------------------------------------------------------------------------

_registry: dict[str, type[Factor]] = {}


def register(cls: type[Factor]) -> type[Factor]:
    """注册因子类到全局注册表。

    必须在类定义上方使用::

        @register
        class MyFactor(Factor):
            ...
    """
    if not cls.name:
        raise ValueError(f"Factor class {cls.__name__} must define 'name'")
    _registry[cls.name] = cls
    return cls


def get_factor(name: str) -> type[Factor] | None:
    """按名称获取已注册的因子类。"""
    return _registry.get(name)


def list_factors() -> list[dict]:
    """列出所有已注册因子的元信息。"""
    return [
        {"name": cls.name, "description": cls.description}
        for cls in _registry.values()
    ]
