"""Shared DB dependency for the HTTP API."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb
from fastapi import HTTPException

from flairbnb.db import connect
from flairbnb.pipeline.util import open_db


def get_con() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    con = open_db(run_migrate=True)
    try:
        yield con
    finally:
        con.close()


def rows_to_dicts(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    cur = con.execute(sql, params or [])
    cols = [c[0] for c in cur.description]
    out = []
    for row in cur.fetchall():
        out.append({cols[i]: _jsonable(row[i]) for i in range(len(cols))})
    return out


def one_or_404(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any],
    detail: str = "Not found",
) -> dict[str, Any]:
    rows = rows_to_dicts(con, sql, params)
    if not rows:
        raise HTTPException(status_code=404, detail=detail)
    return rows[0]


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v
