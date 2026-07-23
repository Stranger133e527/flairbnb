"""Occupancy flip / history resolution tests (local DuckDB)."""

from datetime import date, datetime, timedelta

from flairbnb.db import connect, migrate
from flairbnb.pipeline.occupancy import process_daily_calendar_history


def test_available_to_unavailable_becomes_occupied(tmp_path, monkeypatch):
    db = tmp_path / "occ.duckdb"
    monkeypatch.setenv("FLAIRBNB_DB_PATH", str(db))
    monkeypatch.delenv("motherduck_token", raising=False)
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)

    con = connect()
    migrate(con)
    scraped = datetime(2026, 7, 20, 12, 0, 0)
    night = (date.today() + timedelta(days=5)).isoformat()
    room_id = 42

    day1 = date.today() - timedelta(days=1)
    day2 = date.today()

    # Day 1: open
    process_daily_calendar_history(
        con,
        [
            {
                "room_id": room_id,
                "night": night,
                "available": True,
                "price": None,
                "currency": None,
                "scraped_at": scraped,
            }
        ],
        as_of=day1,
    )
    # Day 2: blocked → flip
    out = process_daily_calendar_history(
        con,
        [
            {
                "room_id": room_id,
                "night": night,
                "available": False,
                "price": None,
                "currency": None,
                "scraped_at": scraped,
            }
        ],
        as_of=day2,
    )
    assert out["flips"] >= 1
    status = con.execute(
        "SELECT status, became_unavailable_on FROM listing_night_history WHERE room_id=? AND night=?",
        [room_id, night],
    ).fetchone()
    assert status[0] == "occupied_inferred"
    assert status[1] == day2
    con.close()
