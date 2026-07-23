"""Shared helpers for sync stages."""

from __future__ import annotations

import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from flairbnb.db import connect, load_env, migrate

UTC = timezone.utc


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default) or default


def scrape_delay() -> None:
    ms = env_int("SCRAPE_DELAY_MS", 200)
    if ms > 0:
        time.sleep(ms / 1000.0)


def new_run_id() -> str:
    return _utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def search_date_window(nights: int | None = None) -> tuple[str, str]:
    nights = nights if nights is not None else env_int("SYNC_SEARCH_NIGHTS", 3)
    check_in = date.today() + timedelta(days=45)
    check_out = check_in + timedelta(days=nights)
    return check_in.isoformat(), check_out.isoformat()


def start_sync_run(con, run_id: str, market_id: str, stage: str) -> None:
    con.execute(
        """
        INSERT INTO sync_runs (run_id, started_at, market_id, stage, status, rows_written)
        VALUES (?, ?, ?, ?, 'running', 0)
        """,
        [run_id, _utcnow(), market_id, stage],
    )


def finish_sync_run(
    con,
    run_id: str,
    status: str,
    rows_written: int = 0,
    error: str | None = None,
) -> None:
    con.execute(
        """
        UPDATE sync_runs
        SET finished_at = ?, status = ?, rows_written = ?, error = ?
        WHERE run_id = ?
        """,
        [_utcnow(), status, rows_written, error, run_id],
    )


def open_db(*, run_migrate: bool = True):
    load_env()
    con = connect()
    if run_migrate:
        migrate(con)
    return con


def geohash_approx(lat: float | None, lng: float | None, precision: int = 6) -> str | None:
    """Lightweight geohash for heatmap bins (base32)."""
    if lat is None or lng is None:
        return None
    try:
        __base32 = "0123456789bcdefghjkmnpqrstuvwxyz"
        lat_interval = [-90.0, 90.0]
        lon_interval = [-180.0, 180.0]
        geohash = []
        bit = 0
        ch = 0
        even = True
        while len(geohash) < precision:
            if even:
                mid = sum(lon_interval) / 2
                if lng > mid:
                    ch |= 1 << (4 - bit)
                    lon_interval[0] = mid
                else:
                    lon_interval[1] = mid
            else:
                mid = sum(lat_interval) / 2
                if lat > mid:
                    ch |= 1 << (4 - bit)
                    lat_interval[0] = mid
                else:
                    lat_interval[1] = mid
            even = not even
            if bit < 4:
                bit += 1
            else:
                geohash.append(__base32[ch])
                bit = 0
                ch = 0
        return "".join(geohash)
    except Exception:
        return None


def nested(d: Any, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default if k == keys[-1] else {})
        if cur is None:
            return default
    return cur if cur != {} else default
