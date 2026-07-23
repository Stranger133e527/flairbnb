"""FastAPI application — MotherDuck-backed analytics API (no frontend)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
import duckdb

from flairbnb.webapi.deps import get_con, one_or_404, rows_to_dicts

app = FastAPI(
    title="Flairbnb API",
    description="India STR analytics warehouse API (MotherDuck). Frontend is separate.",
    version="0.2.0",
)


def run() -> None:
    """CLI entry: flairbnb-api"""
    import uvicorn

    uvicorn.run("flairbnb.webapi.app:app", host="0.0.0.0", port=8000, reload=False)


class SyncRequest(BaseModel):
    stage: Literal["seed", "discover", "enrich", "metrics", "all"] = "metrics"
    markets: str = Field(default="all", description="Comma-separated market ids or 'all'")
    max_listings: int | None = 25
    workers: int | None = 4


@app.get("/health")
def health(con: duckdb.DuckDBPyConnection = Depends(get_con)) -> dict[str, Any]:
    one = con.execute("SELECT 1").fetchone()[0]
    markets = con.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
    listings = con.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    return {"ok": True, "db": one == 1, "markets": markets, "listings": listings}


@app.get("/v1/markets")
def list_markets(
    active_only: bool = True,
    con: duckdb.DuckDBPyConnection = Depends(get_con),
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM markets"
    if active_only:
        sql += " WHERE active"
    sql += " ORDER BY name"
    return rows_to_dicts(con, sql)


@app.get("/v1/markets/{market_id}")
def get_market(market_id: str, con: duckdb.DuckDBPyConnection = Depends(get_con)) -> dict[str, Any]:
    return one_or_404(
        con,
        "SELECT * FROM markets WHERE market_id = ?",
        [market_id],
        detail=f"Market '{market_id}' not found",
    )


@app.get("/v1/markets/{market_id}/kpis")
def market_kpis(market_id: str, con: duckdb.DuckDBPyConnection = Depends(get_con)) -> dict[str, Any]:
    return one_or_404(
        con,
        "SELECT * FROM v_market_kpis WHERE market_id = ?",
        [market_id],
        detail=f"No KPIs for market '{market_id}'",
    )


@app.get("/v1/markets/{market_id}/kpis/2bd")
def market_kpis_2bd(market_id: str, con: duckdb.DuckDBPyConnection = Depends(get_con)) -> dict[str, Any]:
    return one_or_404(
        con,
        "SELECT * FROM v_market_kpis_2bd WHERE market_id = ?",
        [market_id],
        detail=f"No 2bd KPIs for market '{market_id}'",
    )


@app.get("/v1/kpis")
def all_market_kpis(con: duckdb.DuckDBPyConnection = Depends(get_con)) -> list[dict[str, Any]]:
    return rows_to_dicts(
        con,
        "SELECT * FROM v_market_kpis ORDER BY active_listings_live DESC NULLS LAST, name",
    )


@app.get("/v1/markets/{market_id}/by-bedrooms")
def market_by_bedrooms(market_id: str, con: duckdb.DuckDBPyConnection = Depends(get_con)) -> list[dict[str, Any]]:
    return rows_to_dicts(
        con,
        "SELECT * FROM v_market_by_bedrooms WHERE market_id = ? ORDER BY bedrooms",
        [market_id],
    )


@app.get("/v1/markets/{market_id}/by-property-type")
def market_by_property_type(market_id: str, con: duckdb.DuckDBPyConnection = Depends(get_con)) -> list[dict[str, Any]]:
    return rows_to_dicts(
        con,
        "SELECT * FROM v_market_by_property_type WHERE market_id = ? ORDER BY listing_count DESC",
        [market_id],
    )


@app.get("/v1/markets/{market_id}/seasonality")
def market_seasonality(market_id: str, con: duckdb.DuckDBPyConnection = Depends(get_con)) -> list[dict[str, Any]]:
    return rows_to_dicts(
        con,
        "SELECT * FROM v_market_seasonality WHERE market_id = ? ORDER BY year_month",
        [market_id],
    )


@app.get("/v1/markets/{market_id}/forward")
def market_forward(market_id: str, con: duckdb.DuckDBPyConnection = Depends(get_con)) -> list[dict[str, Any]]:
    return rows_to_dicts(
        con,
        "SELECT * FROM v_market_forward_90d WHERE market_id = ? ORDER BY horizon_days",
        [market_id],
    )


@app.get("/v1/markets/{market_id}/score")
def market_score(market_id: str, con: duckdb.DuckDBPyConnection = Depends(get_con)) -> dict[str, Any]:
    return one_or_404(
        con,
        "SELECT * FROM v_market_scores WHERE market_id = ?",
        [market_id],
        detail=f"No score for market '{market_id}'",
    )


@app.get("/v1/markets/{market_id}/hosts")
def market_hosts(
    market_id: str,
    limit: int = Query(50, ge=1, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_con),
) -> list[dict[str, Any]]:
    return rows_to_dicts(
        con,
        """
        SELECT * FROM v_host_concentration
        WHERE market_id = ?
        ORDER BY listing_count DESC
        LIMIT ?
        """,
        [market_id, limit],
    )


@app.get("/v1/markets/{market_id}/listings")
def market_listings(
    market_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    con: duckdb.DuckDBPyConnection = Depends(get_con),
) -> list[dict[str, Any]]:
    return rows_to_dicts(
        con,
        """
        SELECT v.*
        FROM v_listing_latest v
        JOIN listing_markets lm ON v.room_id = lm.room_id
        WHERE lm.market_id = ?
        ORDER BY v.last_seen DESC NULLS LAST
        LIMIT ? OFFSET ?
        """,
        [market_id, limit, offset],
    )


@app.get("/v1/markets/{market_id}/velocity")
def market_velocity(market_id: str, con: duckdb.DuckDBPyConnection = Depends(get_con)) -> list[dict[str, Any]]:
    return rows_to_dicts(
        con,
        """
        SELECT * FROM market_listing_velocity
        WHERE market_id = ?
        ORDER BY as_of DESC
        LIMIT 90
        """,
        [market_id],
    )


@app.get("/v1/markets/{market_id}/amenity-premiums")
def market_amenity_premiums(market_id: str, con: duckdb.DuckDBPyConnection = Depends(get_con)) -> list[dict[str, Any]]:
    return rows_to_dicts(
        con,
        """
        SELECT * FROM amenity_premiums
        WHERE market_id = ?
        ORDER BY as_of DESC, adr_lift DESC NULLS LAST
        """,
        [market_id],
    )


@app.get("/v1/listings/{room_id}")
def get_listing(room_id: int, con: duckdb.DuckDBPyConnection = Depends(get_con)) -> dict[str, Any]:
    return one_or_404(
        con,
        "SELECT * FROM v_listing_latest WHERE room_id = ?",
        [room_id],
        detail=f"Listing '{room_id}' not found",
    )


@app.get("/v1/listings/{room_id}/calendar")
def listing_calendar(
    room_id: int,
    con: duckdb.DuckDBPyConnection = Depends(get_con),
) -> list[dict[str, Any]]:
    rows = rows_to_dicts(
        con,
        """
        SELECT room_id, night, available, price, currency, scraped_at
        FROM calendars
        WHERE room_id = ?
        ORDER BY night
        """,
        [room_id],
    )
    if not rows:
        # still 200 with empty if listing exists
        exists = con.execute("SELECT 1 FROM listings WHERE room_id = ?", [room_id]).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Listing '{room_id}' not found")
    return rows


@app.get("/v1/listings/{room_id}/occupancy-history")
def listing_occupancy_history(
    room_id: int,
    con: duckdb.DuckDBPyConnection = Depends(get_con),
) -> list[dict[str, Any]]:
    return rows_to_dicts(
        con,
        """
        SELECT * FROM listing_night_history
        WHERE room_id = ?
        ORDER BY night
        """,
        [room_id],
    )


@app.get("/v1/events")
def list_events(
    market_id: str | None = None,
    con: duckdb.DuckDBPyConnection = Depends(get_con),
) -> list[dict[str, Any]]:
    if market_id:
        return rows_to_dicts(
            con,
            "SELECT * FROM v_market_events WHERE market_id = ? ORDER BY start_date",
            [market_id],
        )
    return rows_to_dicts(con, "SELECT * FROM v_market_events ORDER BY start_date, market_id")


@app.get("/v1/sync/runs")
def sync_runs(
    limit: int = Query(50, ge=1, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_con),
) -> list[dict[str, Any]]:
    return rows_to_dicts(
        con,
        """
        SELECT run_id, started_at, finished_at, market_id, stage, status, rows_written, error
        FROM sync_runs
        ORDER BY started_at DESC
        LIMIT ?
        """,
        [limit],
    )


@app.get("/v1/analytics/overview")
def analytics_overview(con: duckdb.DuckDBPyConnection = Depends(get_con)) -> dict[str, Any]:
    counts = {
        "markets": con.execute("SELECT COUNT(*) FROM markets WHERE active").fetchone()[0],
        "listings": con.execute("SELECT COUNT(*) FROM listings").fetchone()[0],
        "calendars": con.execute("SELECT COUNT(*) FROM calendars").fetchone()[0],
        "observations": con.execute("SELECT COUNT(*) FROM calendar_observations").fetchone()[0],
        "night_history": con.execute("SELECT COUNT(*) FROM listing_night_history").fetchone()[0],
        "details": con.execute("SELECT COUNT(*) FROM listing_details").fetchone()[0],
    }
    top = rows_to_dicts(
        con,
        """
        SELECT market_id, name, active_listings_live, adr, occupancy_est, revpar, revenue_mo, is_partial
        FROM v_market_kpis
        ORDER BY active_listings_live DESC NULLS LAST
        LIMIT 10
        """,
    )
    last_sync = rows_to_dicts(
        con,
        """
        SELECT run_id, stage, status, started_at, finished_at
        FROM sync_runs ORDER BY started_at DESC LIMIT 1
        """,
    )
    return {
        "counts": counts,
        "top_markets": top,
        "last_sync": last_sync[0] if last_sync else None,
    }


@app.get("/v1/invest/2bd")
def invest_2bd(con: duckdb.DuckDBPyConnection = Depends(get_con)) -> list[dict[str, Any]]:
    """2bd invest view (Tier C columns NULL until external feeds)."""
    return rows_to_dicts(con, "SELECT * FROM v_market_kpis_2bd ORDER BY name")


@app.get("/v1/properties-for-sale")
def properties_for_sale(
    market_id: str | None = None,
    con: duckdb.DuckDBPyConnection = Depends(get_con),
) -> list[dict[str, Any]]:
    if market_id:
        return rows_to_dicts(
            con,
            "SELECT * FROM v_properties_for_sale WHERE market_id = ?",
            [market_id],
        )
    return rows_to_dicts(con, "SELECT * FROM v_properties_for_sale")


def _run_sync(stage: str, markets: str, max_listings: int | None, workers: int | None) -> None:
    from flairbnb.pipeline.sync import main as sync_main

    argv = ["--stage", stage, "--markets", markets]
    if max_listings is not None:
        argv += ["--max-listings", str(max_listings)]
    if workers is not None:
        argv += ["--workers", str(workers)]
    sync_main(argv)


@app.post("/v1/sync/run")
def trigger_sync(body: SyncRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Kick a pipeline stage in the background (ops). Prefer GitHub Actions for production."""
    background_tasks.add_task(_run_sync, body.stage, body.markets, body.max_listings, body.workers)
    return {
        "queued": True,
        "stage": body.stage,
        "markets": body.markets,
        "max_listings": body.max_listings,
        "workers": body.workers,
    }
