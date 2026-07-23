"""Daily calendar observation + occupied-flip resolution."""

from __future__ import annotations

from datetime import date
from typing import Any, Sequence

from flairbnb.pipeline.util import _utcnow


def bulk_insert_observations(con, rows: Sequence[dict[str, Any]], as_of: date | None = None) -> int:
    """Append today's forward-month observations (bulk)."""
    if not rows:
        return 0
    as_of = as_of or date.today()
    payload = [
        (
            int(r["room_id"]),
            r["night"],
            as_of,
            bool(r["available"]),
            r["scraped_at"],
        )
        for r in rows
    ]

    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE _obs_batch (
          room_id BIGINT,
          night DATE,
          as_of DATE,
          available BOOLEAN,
          scraped_at TIMESTAMP
        )
        """
    )
    chunk_size = 2000
    for i in range(0, len(payload), chunk_size):
        chunk = payload[i : i + chunk_size]
        placeholders = ",".join(["(?, ?, ?, ?, ?)"] * len(chunk))
        flat: list[Any] = []
        for tup in chunk:
            flat.extend(tup)
        con.execute(f"INSERT INTO _obs_batch VALUES {placeholders}", flat)

    # Idempotent daily re-run: replace today's slice for these rooms
    con.execute(
        """
        DELETE FROM calendar_observations
        WHERE as_of = ?
          AND room_id IN (SELECT DISTINCT room_id FROM _obs_batch)
        """,
        [as_of],
    )
    con.execute(
        """
        INSERT INTO calendar_observations (room_id, night, as_of, available, scraped_at)
        SELECT room_id, night, as_of, available, scraped_at FROM _obs_batch
        """
    )
    con.execute("DROP TABLE IF EXISTS _obs_batch")
    return len(payload)


def detect_occupancy_flips(con, as_of: date | None = None) -> int:
    """
    Compare today's observations to the previous as_of per (room_id, night).

    available True → False  => became_unavailable (occupied_inferred candidate).
    """
    as_of = as_of or date.today()
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE _flips AS
        WITH today AS (
          SELECT room_id, night, available
          FROM calendar_observations
          WHERE as_of = ?
        ),
        prev AS (
          SELECT o.room_id, o.night, o.available, o.as_of
          FROM calendar_observations o
          JOIN (
            SELECT room_id, night, MAX(as_of) AS prev_as_of
            FROM calendar_observations
            WHERE as_of < ?
            GROUP BY room_id, night
          ) p ON o.room_id = p.room_id AND o.night = p.night AND o.as_of = p.prev_as_of
        )
        SELECT
          t.room_id,
          t.night,
          ? AS detected_on,
          'became_unavailable' AS event_type,
          p.available AS prev_available,
          t.available AS curr_available
        FROM today t
        JOIN prev p ON t.room_id = p.room_id AND t.night = p.night
        WHERE p.available = TRUE AND t.available = FALSE
        """,
        [as_of, as_of, as_of],
    )
    before = con.execute("SELECT COUNT(*) FROM occupancy_events").fetchone()[0]
    con.execute(
        """
        INSERT OR IGNORE INTO occupancy_events (room_id, night, detected_on, event_type, prev_available, curr_available)
        SELECT room_id, night, detected_on, event_type, prev_available, curr_available
        FROM _flips
        """
    )
    after = con.execute("SELECT COUNT(*) FROM occupancy_events").fetchone()[0]
    con.execute("DROP TABLE IF EXISTS _flips")
    return after - before


def resolve_night_history(con, as_of: date | None = None) -> int:
    """
    Rebuild listing_night_history from observations + flip events.

    Past nights (night < as_of) are the source of truth for occupancy metrics:
      - occupied_inferred if we recorded a became_unavailable flip
      - vacant if night passed and last observation was still available
      - always_blocked if we only ever saw unavailable
    Future nights stay open_future / blocked_future for forward demand views.
    """
    as_of = as_of or date.today()
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE _resolved AS
        WITH latest AS (
          SELECT o.room_id, o.night, o.available, o.as_of,
                 ROW_NUMBER() OVER (PARTITION BY o.room_id, o.night ORDER BY o.as_of DESC) AS rn,
                 COUNT(*) OVER (PARTITION BY o.room_id, o.night) AS observation_count,
                 BOOL_OR(o.available) OVER (PARTITION BY o.room_id, o.night) AS ever_available
          FROM calendar_observations o
        ),
        base AS (
          SELECT room_id, night, available AS last_available, observation_count, ever_available
          FROM latest WHERE rn = 1
        ),
        flips AS (
          SELECT room_id, night, MIN(detected_on) AS became_unavailable_on
          FROM occupancy_events
          WHERE event_type = 'became_unavailable'
          GROUP BY room_id, night
        )
        SELECT
          b.room_id,
          b.night,
          CASE
            WHEN f.became_unavailable_on IS NOT NULL THEN 'occupied_inferred'
            WHEN b.night < ? AND b.last_available = TRUE THEN 'vacant'
            WHEN b.night < ? AND b.ever_available = FALSE THEN 'always_blocked'
            WHEN b.night >= ? AND b.last_available = TRUE THEN 'open_future'
            WHEN b.night >= ? AND b.last_available = FALSE THEN 'blocked_future'
            ELSE 'always_blocked'
          END AS status,
          f.became_unavailable_on,
          b.last_available,
          b.observation_count,
          current_timestamp AS updated_at
        FROM base b
        LEFT JOIN flips f ON b.room_id = f.room_id AND b.night = f.night
        """,
        [as_of, as_of, as_of, as_of],
    )
    con.execute("DELETE FROM listing_night_history")
    con.execute(
        """
        INSERT INTO listing_night_history (
          room_id, night, status, became_unavailable_on, last_available, observation_count, updated_at
        )
        SELECT room_id, night, status, became_unavailable_on, last_available, observation_count, updated_at
        FROM _resolved
        """
    )
    n = con.execute("SELECT COUNT(*) FROM listing_night_history").fetchone()[0]
    con.execute("DROP TABLE IF EXISTS _resolved")
    return int(n)


def process_daily_calendar_history(con, rows: Sequence[dict[str, Any]], as_of: date | None = None) -> dict[str, int]:
    """Observations → flip events → resolved night history."""
    as_of = as_of or date.today()
    obs_n = bulk_insert_observations(con, rows, as_of=as_of)
    flips = detect_occupancy_flips(con, as_of=as_of)
    hist = resolve_night_history(con, as_of=as_of)
    return {"observations": obs_n, "flips": flips, "history_rows": hist}
