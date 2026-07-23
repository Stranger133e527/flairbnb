"""Fast MotherDuck bulk writers (avoid per-row INSERT round-trips)."""

from __future__ import annotations

from typing import Any, Sequence


def bulk_replace_calendars(con, rows: Sequence[dict[str, Any]]) -> int:
    """
    Replace calendar nights for the room_ids present in `rows` using one bulk load.

    Pattern: register Arrow/Python batch → DELETE those rooms → INSERT SELECT.
    Avoids per-night ON CONFLICT round-trips (MotherDuck anti-pattern).
    """
    if not rows:
        return 0

    room_ids = sorted({int(r["room_id"]) for r in rows})
    payload = [
        (
            int(r["room_id"]),
            r["night"],
            bool(r["available"]),
            r.get("price"),
            r.get("currency"),
            r["scraped_at"],
        )
        for r in rows
    ]

    # DuckDB can ingest a Python list of tuples as a relation via VALUES batch
    # Build a temp table with a single INSERT...SELECT FROM (VALUES ...).
    # Chunk to keep SQL size reasonable.
    chunk_size = 2000
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE _cal_batch (
          room_id BIGINT,
          night DATE,
          available BOOLEAN,
          price DOUBLE,
          currency VARCHAR,
          scraped_at TIMESTAMP
        )
        """
    )

    for i in range(0, len(payload), chunk_size):
        chunk = payload[i : i + chunk_size]
        # One statement per chunk (still << per-row cloud UPSERTs)
        placeholders = ",".join(["(?, ?, ?, ?, ?, ?)"] * len(chunk))
        flat: list[Any] = []
        for tup in chunk:
            flat.extend(tup)
        con.execute(
            f"INSERT INTO _cal_batch VALUES {placeholders}",
            flat,
        )

    con.execute(
        """
        DELETE FROM calendars
        WHERE room_id IN (SELECT DISTINCT room_id FROM _cal_batch)
        """
    )
    con.execute(
        """
        INSERT INTO calendars (room_id, night, available, price, currency, scraped_at)
        SELECT room_id, night, available, price, currency, scraped_at
        FROM _cal_batch
        """
    )

    # Mark listings refreshed
    scraped_at = rows[0]["scraped_at"]
    placeholders = ",".join(["?"] * len(room_ids))
    con.execute(
        f"""
        UPDATE listings
        SET calendar_scraped_at = ?
        WHERE room_id IN ({placeholders})
        """,
        [scraped_at, *room_ids],
    )
    con.execute("DROP TABLE IF EXISTS _cal_batch")
    return len(payload)
