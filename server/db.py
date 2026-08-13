"""Oracle 连接池。"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator

import oracledb

from server.config import settings

_pool: oracledb.ConnectionPool | None = None


def _cell_to_jsonable(v: Any) -> Any:
    """把 Oracle LOB / Decimal / datetime 转成可 JSON 序列化的值。"""
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, Decimal):
        # 价格等保留小数；整数 Decimal 转 int
        if v == v.to_integral_value():
            try:
                return int(v)
            except Exception:
                return float(v)
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8", errors="replace")
        except Exception:
            return None
    # oracledb LOB
    read = getattr(v, "read", None)
    if callable(read):
        try:
            data = read()
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="replace")
            return data
        except Exception:
            return None
    return v


def init_pool() -> None:
    global _pool
    if _pool is not None:
        return
    _pool = oracledb.create_pool(
        user=settings.oracle_user,
        password=settings.oracle_password.get_secret_value(),
        dsn=settings.oracle_dsn,
        min=1,
        max=8,
        increment=1,
    )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close(force=True)
        _pool = None


@contextmanager
def get_conn() -> Iterator[oracledb.Connection]:
    if _pool is None:
        init_pool()
    assert _pool is not None
    conn = _pool.acquire()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.release(conn)


def next_id(cur: oracledb.Cursor, seq_name: str) -> int:
    cur.execute(f"SELECT {seq_name}.NEXTVAL FROM DUAL")
    return int(cur.fetchone()[0])


def rows_as_dicts(cur: oracledb.Cursor) -> list[dict[str, Any]]:
    cols = [d[0].lower() for d in cur.description]
    out: list[dict[str, Any]] = []
    for row in cur.fetchall():
        out.append({c: _cell_to_jsonable(v) for c, v in zip(cols, row)})
    return out


def row_as_dict(cur: oracledb.Cursor) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0].lower() for d in cur.description]
    return {c: _cell_to_jsonable(v) for c, v in zip(cols, row)}
