"""Pipeline unit tests (local DuckDB, no network)."""

from datetime import date, datetime, timedelta, timezone

from flairbnb.db import connect, migrate
from flairbnb.pipeline.markets import expand_events_for_db, load_markets
from flairbnb.pipeline.metrics import compute_metrics, REGULATION_PENALTY
from flairbnb.pipeline.seed import seed_markets
from flairbnb.pipeline.util import geohash_approx, search_date_window


def test_load_twenty_markets():
    markets = load_markets()
    assert len(markets) == 20
    ids = {m["id"] for m in markets}
    assert "mumbai" in ids
    assert "candolim" in ids
    candolim = next(m for m in markets if m["id"] == "candolim")
    assert candolim["regulation"] == "High"


def test_expand_events():
    rows = expand_events_for_db()
    assert any(r["event_id"] == "diwali_2026" for r in rows)
    assert any(r["market_id"] == "mumbai" and r["event_id"] == "ipl_window" for r in rows)


def test_geohash_and_dates():
    assert geohash_approx(12.97, 77.59)
    a, b = search_date_window(3)
    assert a < b


def test_seed_and_metrics_local(tmp_path, monkeypatch):
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("FLAIRBNB_DB_PATH", str(db_path))
    monkeypatch.delenv("motherduck_token", raising=False)
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)

    con = connect()
    migrate(con)
    n = seed_markets(con=con)
    assert n >= 20

    # Seed a fake listing + calendar + snapshot for mumbai
    as_of = datetime.now(timezone.utc).replace(tzinfo=None)
    con.execute(
        """
        INSERT INTO listings (room_id, title, latitude, longitude, bedrooms, property_type,
          host_id, first_seen, last_seen)
        VALUES (1, 'Test', 19.1, 72.8, 2, 'Entire home/apt', 'h1', ?, ?)
        """,
        [as_of, as_of],
    )
    con.execute("INSERT INTO listing_markets VALUES (1, 'mumbai')")
    con.execute(
        """
        INSERT INTO listing_search_snapshots (
          as_of, market_id, room_id, search_price, currency, rating_value, review_count,
          latitude, longitude, title, badges
        ) VALUES (?, 'mumbai', 1, 5000, 'INR', 4.8, 10, 19.1, 72.8, 'Test', '[]')
        """,
        [as_of],
    )
    for i in range(40):
        night = date.today() - timedelta(days=i + 1)
        status = "occupied_inferred" if i % 3 != 0 else "vacant"
        con.execute(
            """
            INSERT INTO listing_night_history (
              room_id, night, status, became_unavailable_on, last_available, observation_count, updated_at
            ) VALUES (1, ?, ?, ?, ?, 2, ?)
            """,
            [night, status, night if status == "occupied_inferred" else None, status == "vacant", as_of],
        )
        # also keep a bit of forward calendar for fallback paths
        if i < 5:
            fwd = date.today() + timedelta(days=i + 1)
            con.execute(
                "INSERT INTO calendars VALUES (1, ?, ?, NULL, NULL, ?)",
                [fwd, i % 2 == 0, as_of],
            )

    rows = compute_metrics(con=con)
    assert rows == 20

    kpi = con.execute(
        "SELECT active_listings_live, adr, occupancy_est, revpar FROM market_kpi_daily WHERE market_id = 'mumbai'"
    ).fetchone()
    assert kpi[0] == 1
    assert kpi[1] == 5000
    assert kpi[2] is not None and kpi[2] > 0
    assert kpi[3] is not None

    view = con.execute("SELECT name, regulation FROM v_market_kpis WHERE market_id = 'mumbai'").fetchone()
    assert view[0].startswith("Mumbai")
    assert view[1] == "Low"

    assert REGULATION_PENALTY["High"] > REGULATION_PENALTY["Low"]
    con.close()
