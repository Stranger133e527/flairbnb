"""MotherDuck / local DuckDB connection helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path

import duckdb
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
_SQL_DIR = _ROOT / "sql"


def load_env() -> None:
    load_dotenv(_ROOT / ".env", override=False)


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Connect to MotherDuck (md:) or local DuckDB file via FLAIRBNB_DB_PATH."""
    load_env()
    local_path = os.getenv("FLAIRBNB_DB_PATH")
    if local_path:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(local_path, read_only=read_only)

    token = os.getenv("motherduck_token") or os.getenv("MOTHERDUCK_TOKEN")
    database = os.getenv("MOTHERDUCK_DATABASE", "flairbnb")
    if not token:
        fallback = _ROOT / "data" / "flairbnb.duckdb"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(fallback), read_only=read_only)

    os.environ.setdefault("motherduck_token", token)
    return duckdb.connect(f"md:{database}")


def _split_sql(sql: str) -> list[str]:
    # Strip line comments, split on semicolons
    lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    parts = [p.strip() for p in cleaned.split(";")]
    return [p for p in parts if p]


def run_sql_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    for stmt in _split_sql(path.read_text(encoding="utf-8")):
        con.execute(stmt)


def migrate(con: duckdb.DuckDBPyConnection | None = None) -> duckdb.DuckDBPyConnection:
    own = con is None
    if own:
        con = connect()
    for name in (
        "001_init.sql",
        "002_views.sql",
        "003_calendar_history.sql",
        "004_p1_analytics.sql",
    ):
        run_sql_file(con, _SQL_DIR / name)
    return con
