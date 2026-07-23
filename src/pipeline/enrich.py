"""Enrichment stage: details + calendars (+ optional price quotes)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import flairbnb
from flairbnb.pipeline.markets import load_markets
from flairbnb.pipeline.util import (
    env_int,
    env_str,
    finish_sync_run,
    nested,
    new_run_id,
    open_db,
    scrape_delay,
    start_sync_run,
    _utcnow,
)


def _parse_calendar_months(months: list) -> list[dict]:
    rows = []
    scraped_at = _utcnow()
    for month in months or []:
        for day in month.get("days") or []:
            night = day.get("calendarDate") or day.get("date")
            if not night:
                continue
            available = day.get("available")
            if available is None:
                available = day.get("availability") == "available"
            price = None
            currency = None
            price_info = day.get("price") or {}
            if isinstance(price_info, dict):
                amount = price_info.get("amount") or price_info.get("localPrice")
                if amount is not None:
                    try:
                        price = float(amount)
                    except Exception:
                        price = None
                currency = price_info.get("currency")
            rows.append(
                {
                    "night": night,
                    "available": bool(available),
                    "price": price,
                    "currency": currency,
                    "scraped_at": scraped_at,
                }
            )
    return rows


def _apply_details(con, room_id: int, data: dict) -> None:
    scraped_at = _utcnow()
    host = data.get("host") or {}
    host_id = str(host.get("id") or "") or None
    bedrooms = data.get("bedrooms") or nested(data, "room", "bedrooms")
    beds = data.get("beds") or nested(data, "room", "beds")
    bathrooms = data.get("bathrooms") or nested(data, "room", "bathrooms")
    person_capacity = data.get("person_capacity") or nested(data, "room", "personCapacity")
    property_type = data.get("room_type") or data.get("property_type") or nested(data, "room", "roomType")
    rating = data.get("rating") or {}
    rating_value = rating.get("value") if isinstance(rating, dict) else None
    review_count = rating.get("reviewCount") if isinstance(rating, dict) else None
    is_superhost = bool(host.get("is_superhost") or host.get("isSuperhost") or False)
    images = data.get("images") or data.get("photos") or []
    photo_count = len(images) if isinstance(images, list) else None
    amenities = data.get("amenities") or []
    amenity_count = 0
    if isinstance(amenities, list):
        for group in amenities:
            if isinstance(group, dict):
                amenity_count += len(group.get("values") or [])
            else:
                amenity_count += 1

    con.execute(
        """
        INSERT INTO listing_details (
          room_id, scraped_at, host_id, bedrooms, beds, bathrooms, person_capacity,
          property_type, rating_value, review_count, is_superhost, photo_count,
          amenity_count, amenities_json, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (room_id) DO UPDATE SET
          scraped_at = excluded.scraped_at,
          host_id = COALESCE(excluded.host_id, listing_details.host_id),
          bedrooms = COALESCE(excluded.bedrooms, listing_details.bedrooms),
          beds = COALESCE(excluded.beds, listing_details.beds),
          bathrooms = COALESCE(excluded.bathrooms, listing_details.bathrooms),
          person_capacity = COALESCE(excluded.person_capacity, listing_details.person_capacity),
          property_type = COALESCE(excluded.property_type, listing_details.property_type),
          rating_value = COALESCE(excluded.rating_value, listing_details.rating_value),
          review_count = COALESCE(excluded.review_count, listing_details.review_count),
          is_superhost = COALESCE(excluded.is_superhost, listing_details.is_superhost),
          photo_count = COALESCE(excluded.photo_count, listing_details.photo_count),
          amenity_count = COALESCE(excluded.amenity_count, listing_details.amenity_count),
          amenities_json = excluded.amenities_json,
          raw_json = excluded.raw_json
        """,
        [
            room_id,
            scraped_at,
            host_id,
            bedrooms,
            beds,
            bathrooms,
            person_capacity,
            property_type,
            rating_value,
            int(review_count) if review_count not in (None, "") else None,
            is_superhost,
            photo_count,
            amenity_count,
            json.dumps(amenities)[:20000] if amenities else None,
            json.dumps(data)[:50000],
        ],
    )

    con.execute(
        """
        UPDATE listings SET
          host_id = COALESCE(?, host_id),
          bedrooms = COALESCE(?, bedrooms),
          beds = COALESCE(?, beds),
          bathrooms = COALESCE(?, bathrooms),
          person_capacity = COALESCE(?, person_capacity),
          property_type = COALESCE(?, property_type),
          rating_value = COALESCE(?, rating_value),
          review_count = COALESCE(?, review_count),
          is_superhost = COALESCE(?, is_superhost),
          photo_count = COALESCE(?, photo_count),
          amenity_count = COALESCE(?, amenity_count),
          details_scraped_at = ?
        WHERE room_id = ?
        """,
        [
            host_id,
            bedrooms,
            beds,
            bathrooms,
            person_capacity,
            property_type,
            rating_value,
            int(review_count) if review_count not in (None, "") else None,
            is_superhost,
            photo_count,
            amenity_count,
            scraped_at,
            room_id,
        ],
    )

    if host_id:
        con.execute(
            """
            INSERT INTO hosts (host_id, name, is_superhost, scraped_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (host_id) DO UPDATE SET
              name = COALESCE(excluded.name, hosts.name),
              is_superhost = COALESCE(excluded.is_superhost, hosts.is_superhost),
              scraped_at = excluded.scraped_at
            """,
            [host_id, host.get("name") or host.get("host_name"), is_superhost, scraped_at],
        )


def enrich_market(market_id: str, con=None) -> dict[str, int]:
    own = con is None
    if own:
        con = open_db()

    run_id = new_run_id()
    start_sync_run(con, run_id, market_id, "enrich")
    proxy = env_str("FLAIRBNB_PROXY_URL", "")
    language = env_str("FLAIRBNB_LANGUAGE", "en")
    currency = env_str("FLAIRBNB_CURRENCY", "INR")
    cal_limit = env_int("SYNC_CALENDAR_REFRESH_LIMIT", 200)
    details_limit = env_int("SYNC_DETAILS_REFRESH_LIMIT", 50)

    details_n = 0
    calendar_n = 0
    try:
        # Details for new/stale listings
        detail_targets = con.execute(
            """
            SELECT l.room_id
            FROM listings l
            JOIN listing_markets lm ON l.room_id = lm.room_id
            WHERE lm.market_id = ?
              AND (l.details_scraped_at IS NULL
                   OR l.details_scraped_at < current_timestamp - INTERVAL '7 days')
            ORDER BY l.details_scraped_at NULLS FIRST, l.last_seen DESC
            LIMIT ?
            """,
            [market_id, details_limit],
        ).fetchall()

        for (room_id,) in detail_targets:
            try:
                data = flairbnb.get_details(
                    room_id=int(room_id),
                    currency=currency,
                    language=language,
                    proxy_url=proxy,
                    timeout=60,
                )
                _apply_details(con, int(room_id), data)
                details_n += 1
            except Exception as exc:
                print(f"[enrich:details] {room_id}: {exc}")
            scrape_delay()

        # Calendars for stale listings
        cal_targets = con.execute(
            """
            SELECT l.room_id
            FROM listings l
            JOIN listing_markets lm ON l.room_id = lm.room_id
            WHERE lm.market_id = ?
              AND (l.calendar_scraped_at IS NULL
                   OR l.calendar_scraped_at < current_timestamp - INTERVAL '1 day')
            ORDER BY l.calendar_scraped_at NULLS FIRST, l.last_seen DESC
            LIMIT ?
            """,
            [market_id, cal_limit],
        ).fetchall()

        for (room_id,) in cal_targets:
            try:
                months = flairbnb.get_calendar(room_id=str(room_id), proxy_url=proxy, timeout=60)
                nights = _parse_calendar_months(months if isinstance(months, list) else [])
                scraped_at = _utcnow()
                for n in nights:
                    con.execute(
                        """
                        INSERT INTO calendars (room_id, night, available, price, currency, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT (room_id, night) DO UPDATE SET
                          available = excluded.available,
                          price = COALESCE(excluded.price, calendars.price),
                          currency = COALESCE(excluded.currency, calendars.currency),
                          scraped_at = excluded.scraped_at
                        """,
                        [
                            int(room_id),
                            n["night"],
                            n["available"],
                            n["price"],
                            n["currency"],
                            n["scraped_at"],
                        ],
                    )
                    calendar_n += 1
                con.execute(
                    "UPDATE listings SET calendar_scraped_at = ? WHERE room_id = ?",
                    [scraped_at, int(room_id)],
                )
            except Exception as exc:
                print(f"[enrich:calendar] {room_id}: {exc}")
            scrape_delay()

        # Optional: one price quote sample for a few listings
        quote_limit = min(10, details_limit)
        quote_targets = con.execute(
            """
            SELECT l.room_id FROM listings l
            JOIN listing_markets lm ON l.room_id = lm.room_id
            WHERE lm.market_id = ?
            ORDER BY l.last_seen DESC
            LIMIT ?
            """,
            [market_id, quote_limit],
        ).fetchall()
        check_in = date.today() + timedelta(days=30)
        check_out = check_in + timedelta(days=3)
        for (room_id,) in quote_targets:
            try:
                price = flairbnb.get_price(
                    room_id=str(room_id),
                    check_in=check_in,
                    check_out=check_out,
                    currency=currency,
                    language=language,
                    proxy_url=proxy,
                    timeout=60,
                )
                total = None
                nightly = None
                if isinstance(price, dict):
                    total = price.get("total") or nested(price, "price", "total", "amount")
                    nights = (check_out - check_in).days or 1
                    if total is not None:
                        try:
                            total = float(total)
                            nightly = total / nights
                        except Exception:
                            total = None
                if total is not None:
                    con.execute(
                        """
                        INSERT INTO price_quotes (
                          room_id, check_in, check_out, adults, currency, total, nightly, scraped_at
                        ) VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                        ON CONFLICT (room_id, check_in, check_out, adults) DO UPDATE SET
                          total = excluded.total,
                          nightly = excluded.nightly,
                          scraped_at = excluded.scraped_at
                        """,
                        [
                            int(room_id),
                            check_in,
                            check_out,
                            currency,
                            total,
                            nightly,
                            _utcnow(),
                        ],
                    )
            except Exception as exc:
                print(f"[enrich:price] {room_id}: {exc}")
            scrape_delay()

        rows = details_n + calendar_n
        finish_sync_run(con, run_id, "ok", rows_written=rows)
        return {"details": details_n, "calendar_nights": calendar_n}
    except Exception as exc:
        finish_sync_run(con, run_id, "error", error=str(exc))
        raise
    finally:
        if own:
            con.close()


def enrich_all(
    market_ids: list[str] | None = None,
    con=None,
    workers: int | None = None,
) -> dict[str, dict]:
    """Enrich markets; use workers>1 to scrape markets in parallel (each gets own DB conn)."""
    ids = market_ids or [m["id"] for m in load_markets()]
    workers = workers if workers is not None else env_int("SYNC_ENRICH_WORKERS", 4)
    workers = max(1, min(workers, len(ids) or 1))

    def _one(mid: str) -> tuple[str, dict]:
        print(f"[enrich] starting {mid} ...", flush=True)
        try:
            # Own connection per worker — do not share DuckDB/MotherDuck conns across threads
            result = enrich_market(mid, con=None)
            print(f"[enrich] {mid}: {result}", flush=True)
            return mid, result
        except Exception as exc:
            print(f"[enrich] {mid} failed: {exc}", flush=True)
            return mid, {"error": str(exc)}

    if workers == 1:
        # Keep optional shared con for sequential path
        own = con is None
        if own:
            con = open_db()
        out: dict[str, dict] = {}
        try:
            for mid in ids:
                print(f"[enrich] starting {mid} ...", flush=True)
                try:
                    out[mid] = enrich_market(mid, con=con)
                    print(f"[enrich] {mid}: {out[mid]}", flush=True)
                except Exception as exc:
                    out[mid] = {"error": str(exc)}
                    print(f"[enrich] {mid} failed: {exc}", flush=True)
            return out
        finally:
            if own:
                con.close()

    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_one, mid): mid for mid in ids}
        for fut in as_completed(futures):
            mid, result = fut.result()
            out[mid] = result
    return out
