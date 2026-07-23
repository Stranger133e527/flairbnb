"""Discovery stage: map search → listings + search snapshots."""

from __future__ import annotations

import json
from datetime import datetime

import flairbnb
from flairbnb.pipeline.markets import get_market, load_markets
from flairbnb.pipeline.util import (
    env_int,
    env_str,
    finish_sync_run,
    geohash_approx,
    new_run_id,
    open_db,
    scrape_delay,
    search_date_window,
    start_sync_run,
)
from flairbnb.pipeline.util import _utcnow


def _normalize_search_row(row: dict, market_id: str, as_of: datetime) -> dict:
    lat = row.get("coordinates", {}).get("latitude")
    lng = row.get("coordinates", {}).get("longitud") or row.get("coordinates", {}).get("longitude")
    price = row.get("price", {}).get("unit", {}).get("amount")
    currency = row.get("price", {}).get("unit", {}).get("curency_symbol") or env_str(
        "FLAIRBNB_CURRENCY", "INR"
    )
    rating = row.get("rating") or {}
    review_count = rating.get("reviewCount") or 0
    try:
        review_count = int(str(review_count).replace(",", ""))
    except Exception:
        review_count = 0
    return {
        "as_of": as_of,
        "market_id": market_id,
        "room_id": int(row.get("room_id") or 0),
        "search_price": float(price) if price not in (None, "") else None,
        "currency": currency,
        "price_qualifier": row.get("price", {}).get("unit", {}).get("qualifier"),
        "rating_value": rating.get("value") or None,
        "review_count": review_count,
        "latitude": lat,
        "longitude": lng,
        "title": row.get("title") or row.get("name"),
        "badges": json.dumps(row.get("badges") or []),
        "name": row.get("name"),
        "geohash": geohash_approx(lat, lng),
    }


def discover_market(market_id: str, con=None, max_listings: int | None = None) -> int:
    own = con is None
    if own:
        con = open_db()

    market = get_market(market_id)
    run_id = new_run_id()
    start_sync_run(con, run_id, market_id, "discover")
    as_of = _utcnow()
    check_in, check_out = search_date_window()
    currency = env_str("FLAIRBNB_CURRENCY", "INR")
    language = env_str("FLAIRBNB_LANGUAGE", "en")
    proxy = env_str("FLAIRBNB_PROXY_URL", "")
    zoom = int(market.get("zoom") or env_int("SYNC_ZOOM", 12))
    cap = max_listings if max_listings is not None else env_int("SYNC_MAX_LISTINGS_PER_MARKET", 0)

    rows_written = 0
    try:
        # Fast path: capped runs use first page only (seconds/market, not minutes).
        # Full pagination (search_all) only when uncapped — that is the slow path.
        search_kwargs = dict(
            check_in=check_in,
            check_out=check_out,
            ne_lat=market["ne_lat"],
            ne_long=market["ne_lng"],
            sw_lat=market["sw_lat"],
            sw_long=market["sw_lng"],
            zoom_value=zoom,
            price_min=0,
            price_max=0,
            currency=currency,
            language=language,
            proxy_url=proxy,
            timeout=60,
        )
        if cap > 0:
            results = flairbnb.search_first_page(**search_kwargs)
            results = results[:cap]
        else:
            results = flairbnb.search_all(**search_kwargs)
        scrape_delay()

        for raw in results:
            n = _normalize_search_row(raw, market_id, as_of)
            if not n["room_id"]:
                continue

            con.execute(
                """
                INSERT INTO listing_search_snapshots (
                  as_of, market_id, room_id, search_price, currency, price_qualifier,
                  rating_value, review_count, latitude, longitude, title, badges
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    n["as_of"],
                    n["market_id"],
                    n["room_id"],
                    n["search_price"],
                    n["currency"],
                    n["price_qualifier"],
                    n["rating_value"],
                    n["review_count"],
                    n["latitude"],
                    n["longitude"],
                    n["title"],
                    n["badges"],
                ],
            )

            con.execute(
                """
                INSERT INTO listings (
                  room_id, title, name, latitude, longitude, geohash,
                  rating_value, review_count, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (room_id) DO UPDATE SET
                  title = COALESCE(excluded.title, listings.title),
                  name = COALESCE(excluded.name, listings.name),
                  latitude = COALESCE(excluded.latitude, listings.latitude),
                  longitude = COALESCE(excluded.longitude, listings.longitude),
                  geohash = COALESCE(excluded.geohash, listings.geohash),
                  rating_value = COALESCE(excluded.rating_value, listings.rating_value),
                  review_count = COALESCE(excluded.review_count, listings.review_count),
                  last_seen = excluded.last_seen
                """,
                [
                    n["room_id"],
                    n["title"],
                    n["name"],
                    n["latitude"],
                    n["longitude"],
                    n["geohash"],
                    n["rating_value"],
                    n["review_count"],
                    as_of,
                    as_of,
                ],
            )

            con.execute(
                """
                INSERT OR IGNORE INTO listing_markets (room_id, market_id)
                VALUES (?, ?)
                """,
                [n["room_id"], market_id],
            )
            rows_written += 1

        finish_sync_run(con, run_id, "ok", rows_written=rows_written)
        return rows_written
    except Exception as exc:
        finish_sync_run(con, run_id, "error", rows_written=rows_written, error=str(exc))
        raise
    finally:
        if own:
            con.close()


def discover_all(market_ids: list[str] | None = None, con=None) -> dict[str, int]:
    own = con is None
    if own:
        con = open_db()
    ids = market_ids or [m["id"] for m in load_markets()]
    out: dict[str, int] = {}
    try:
        for mid in ids:
            print(f"[discover] starting {mid} ...", flush=True)
            try:
                out[mid] = discover_market(mid, con=con)
                print(f"[discover] {mid}: {out[mid]} listings", flush=True)
            except Exception as exc:
                out[mid] = -1
                print(f"[discover] {mid} failed: {exc}", flush=True)
        return out
    finally:
        if own:
            con.close()
