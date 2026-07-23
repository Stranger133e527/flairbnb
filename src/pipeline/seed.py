"""Seed markets + India events into the warehouse."""

from __future__ import annotations

from flairbnb.pipeline.markets import expand_events_for_db, load_markets
from flairbnb.pipeline.util import finish_sync_run, new_run_id, open_db, start_sync_run


def seed_markets(con=None) -> int:
    own = con is None
    if own:
        con = open_db()
    run_id = new_run_id()
    start_sync_run(con, run_id, "all", "seed")
    rows = 0
    try:
        for m in load_markets():
            con.execute(
                """
                INSERT OR REPLACE INTO markets (
                  market_id, name, state, regulation, ne_lat, ne_lng, sw_lat, sw_lng, zoom, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE)
                """,
                [
                    m["id"],
                    m["name"],
                    m.get("state"),
                    m["regulation"],
                    m["ne_lat"],
                    m["ne_lng"],
                    m["sw_lat"],
                    m["sw_lng"],
                    m.get("zoom", 12),
                ],
            )
            rows += 1

        con.execute("DELETE FROM market_events")
        for ev in expand_events_for_db():
            con.execute(
                """
                INSERT INTO market_events (event_id, name, start_date, end_date, demand, market_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    ev["event_id"],
                    ev["name"],
                    ev["start_date"],
                    ev["end_date"],
                    ev["demand"],
                    ev["market_id"],
                ],
            )
            rows += 1

        # Default opex rows
        for m in load_markets():
            con.execute(
                """
                INSERT OR IGNORE INTO opex_defaults (market_id)
                VALUES (?)
                """,
                [m["id"]],
            )

        finish_sync_run(con, run_id, "ok", rows_written=rows)
        return rows
    except Exception as exc:
        finish_sync_run(con, run_id, "error", error=str(exc))
        raise
    finally:
        if own:
            con.close()
