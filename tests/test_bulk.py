"""Bulk calendar writer unit test (local DuckDB)."""

from datetime import datetime

from flairbnb.db import connect, migrate
from flairbnb.pipeline.bulk import bulk_replace_calendars


def test_bulk_replace_calendars(tmp_path, monkeypatch):
    db = tmp_path / "t.duckdb"
    monkeypatch.setenv("FLAIRBNB_DB_PATH", str(db))
    monkeypatch.delenv("motherduck_token", raising=False)
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)

    con = connect()
    migrate(con)
    con.execute(
        "INSERT INTO listings (room_id, title, first_seen, last_seen) VALUES (99, 'x', current_timestamp, current_timestamp)"
    )
    scraped = datetime(2026, 7, 23, 12, 0, 0)
    rows = [
        {
            "room_id": 99,
            "night": f"2026-08-{d:02d}",
            "available": d % 2 == 0,
            "price": None,
            "currency": None,
            "scraped_at": scraped,
        }
        for d in range(1, 11)
    ]
    n = bulk_replace_calendars(con, rows)
    assert n == 10
    assert con.execute("SELECT COUNT(*) FROM calendars WHERE room_id=99").fetchone()[0] == 10
    # replace again with fewer nights
    n2 = bulk_replace_calendars(con, rows[:3])
    assert n2 == 3
    assert con.execute("SELECT COUNT(*) FROM calendars WHERE room_id=99").fetchone()[0] == 3
    con.close()
