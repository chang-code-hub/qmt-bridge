"""因子数据库层 —— SQLAlchemy Core 动态表操作。

每个因子使用独立的 PostgreSQL 表，表名格式为 ``factor_{name}``。
表结构由因子的 ``db_columns()`` 方法动态定义，数据不再存 JSONB，
而是展开为独立的表列，便于 SQL 查询和索引。
"""

from datetime import date as dt_date
from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from ..config import Settings
from .base import get_factor


# ---------------------------------------------------------------------------
# 动态表创建
# ---------------------------------------------------------------------------

_cached_tables: dict[str, Table] = {}


def _factor_table_name(factor_name: str) -> str:
    return f"factor_{factor_name}"


def ensure_factor_table(engine: Engine, factor_name: str) -> Table:
    """确保指定因子的表已存在，返回 Table 对象（带缓存）。"""
    if factor_name in _cached_tables:
        return _cached_tables[factor_name]

    factor_cls = get_factor(factor_name)
    if factor_cls is None:
        raise ValueError(f"未知因子: {factor_name}")

    extra_columns = factor_cls.db_columns()
    if not extra_columns:
        raise ValueError(
            f"因子 {factor_name} 未覆盖 db_columns()，无法创建数据表"
        )

    table_name = _factor_table_name(factor_name)
    metadata = MetaData()
    table = Table(
        table_name,
        metadata,
        Column("id", Integer, primary_key=True),
        Column("stock_code", String(12), nullable=False),
        Column("trade_date", Date, nullable=False),
        *extra_columns,
        Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
        UniqueConstraint("stock_code", "trade_date", name=f"uix_{table_name}"),
    )
    metadata.create_all(engine, tables=[table], checkfirst=True)
    _cached_tables[factor_name] = table
    return table


# ---------------------------------------------------------------------------
# Engine 工厂
# ---------------------------------------------------------------------------


def make_engine(settings: Settings) -> Engine:
    """根据 Settings 创建 SQLAlchemy Engine。"""
    from sqlalchemy import URL

    url = URL.create(
        drivername="postgresql+psycopg2",
        username=settings.pg_user,
        password=settings.pg_password,
        host=settings.pg_host,
        port=settings.pg_port,
        database=settings.pg_database,
    )
    return create_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        future=True,
    )


# ---------------------------------------------------------------------------
# 表管理
# ---------------------------------------------------------------------------


def create_tables(engine: Engine) -> None:
    """为所有已注册因子创建表（若不存在）。"""
    from .base import list_factors

    for meta in list_factors():
        ensure_factor_table(engine, meta["name"])


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def _extract_db_record(table: Table, record: dict) -> dict:
    """将包含 factor_data 的 record 展开为表各列的字典。"""
    db_rec = {
        "stock_code": record["stock_code"],
        "trade_date": record["trade_date"],
        "updated_at": datetime.utcnow(),
    }
    factor_data = record.get("factor_data", {})
    for col in table.columns:
        col_name = col.name
        if col_name in ("id", "stock_code", "trade_date", "updated_at"):
            continue
        db_rec[col_name] = factor_data.get(col_name)
    return db_rec


def _row_to_dict(table: Table, row) -> dict:
    """将查询结果行组装为兼容的响应字典。"""
    trade_date = row.trade_date.strftime("%Y%m%d")
    factor_data = {}
    for col in table.columns:
        col_name = col.name
        if col_name in ("id", "stock_code", "trade_date", "updated_at"):
            continue
        factor_data[col_name] = getattr(row, col_name)
    return {
        "trade_date": trade_date,
        "factor_data": factor_data,
    }


def upsert_factors(engine: Engine, factor_name: str, records: list[dict]) -> int:
    """批量写入或更新指定因子的记录。

    Args:
        engine: SQLAlchemy Engine。
        factor_name: 因子名称，用于定位对应的表。
        records: 每条记录含 ``stock_code``、``trade_date``、``factor_data`` 键。

    Returns:
        写入的记录数。
    """
    if not records:
        return 0

    table = ensure_factor_table(engine, factor_name)
    db_records = [_extract_db_record(table, r) for r in records]

    with engine.begin() as conn:
        stmt = pg_insert(table).values(db_records)
        update_cols = {
            c.name: stmt.excluded[c.name]
            for c in table.columns
            if c.name not in ("id", "stock_code", "trade_date", "updated_at")
        }
        update_cols["updated_at"] = stmt.excluded["updated_at"]
        update_stmt = stmt.on_conflict_do_update(
            index_elements=["stock_code", "trade_date"],
            set_=update_cols,
        )
        conn.execute(update_stmt)
    return len(db_records)


def query_factors(
    engine: Engine,
    factor_name: str,
    stock_codes: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """查询指定因子、指定股票的历史数据。

    Args:
        engine: SQLAlchemy Engine。
        factor_name: 因子名称，用于定位对应的表。
        stock_codes: 股票代码列表。
        start_date: 起始日期（YYYYMMDD），可选。
        end_date: 结束日期（YYYYMMDD），可选。

    Returns:
        按 trade_date 升序排列的记录列表，每条为 ``{"trade_date": "...", "factor_data": {...}}``。
    """
    table = ensure_factor_table(engine, factor_name)

    with engine.begin() as conn:
        stmt = (
            select(*table.columns)
            .where(table.c.stock_code.in_(stock_codes))
            .order_by(table.c.trade_date)
        )
        if start_date:
            y, m, d = int(start_date[:4]), int(start_date[4:6]), int(start_date[6:])
            stmt = stmt.where(table.c.trade_date >= dt_date(y, m, d))
        if end_date:
            y, m, d = int(end_date[:4]), int(end_date[4:6]), int(end_date[6:])
            stmt = stmt.where(table.c.trade_date <= dt_date(y, m, d))

        rows = conn.execute(stmt).all()
        return [_row_to_dict(table, row) for row in rows]
