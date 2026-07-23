"""Compute market KPIs and P0 analytics tables."""

from __future__ import annotations

from datetime import date, datetime

from flairbnb.pipeline.markets import load_markets
from flairbnb.pipeline.util import finish_sync_run, new_run_id, open_db, start_sync_run

REGULATION_PENALTY = {"Low": 0.0, "Moderate": 0.05, "High": 0.15}


def compute_metrics(con=None, as_of: date | None = None) -> int:
    own = con is None
    if own:
        con = open_db()
    as_of = as_of or date.today()
    run_id = new_run_id()
    start_sync_run(con, run_id, "all", "metrics")
    rows = 0
    try:
        # Update host listing_count
        con.execute(
            """
            UPDATE hosts SET listing_count = s.cnt
            FROM (
              SELECT host_id, COUNT(*) AS cnt FROM listings
              WHERE host_id IS NOT NULL GROUP BY host_id
            ) s
            WHERE hosts.host_id = s.host_id
            """
        )

        markets = [m["id"] for m in load_markets()]
        for market_id in markets:
            rows += _compute_market(con, market_id, as_of)

        finish_sync_run(con, run_id, "ok", rows_written=rows)
        return rows
    except Exception as exc:
        finish_sync_run(con, run_id, "error", error=str(exc))
        raise
    finally:
        if own:
            con.close()


def _compute_market(con, market_id: str, as_of: date) -> int:
    # Active listings
    active_ttm = con.execute(
        """
        SELECT COUNT(DISTINCT l.room_id)
        FROM listings l
        JOIN listing_markets lm ON l.room_id = lm.room_id
        WHERE lm.market_id = ?
          AND l.last_seen >= current_timestamp - INTERVAL '365 days'
        """,
        [market_id],
    ).fetchone()[0]

    active_live = con.execute(
        """
        SELECT COUNT(DISTINCT l.room_id)
        FROM listings l
        JOIN listing_markets lm ON l.room_id = lm.room_id
        WHERE lm.market_id = ?
          AND l.last_seen >= current_timestamp - INTERVAL '14 days'
        """,
        [market_id],
    ).fetchone()[0]

    # ADR from price quotes then search snapshots
    adr_row = con.execute(
        """
        WITH quote_adr AS (
          SELECT AVG(nightly) AS adr,
                 quantile_cont(nightly, 0.25) AS p25,
                 quantile_cont(nightly, 0.50) AS p50,
                 quantile_cont(nightly, 0.75) AS p75
          FROM price_quotes pq
          JOIN listing_markets lm ON pq.room_id = lm.room_id
          WHERE lm.market_id = ?
            AND pq.scraped_at >= current_timestamp - INTERVAL '30 days'
            AND pq.nightly > 0
        ),
        search_adr AS (
          SELECT AVG(search_price) AS adr,
                 quantile_cont(search_price, 0.25) AS p25,
                 quantile_cont(search_price, 0.50) AS p50,
                 quantile_cont(search_price, 0.75) AS p75
          FROM listing_search_snapshots
          WHERE market_id = ?
            AND as_of >= current_timestamp - INTERVAL '30 days'
            AND search_price > 0
        )
        SELECT
          COALESCE((SELECT adr FROM quote_adr), (SELECT adr FROM search_adr)) AS adr,
          COALESCE((SELECT p25 FROM quote_adr), (SELECT p25 FROM search_adr)) AS p25,
          COALESCE((SELECT p50 FROM quote_adr), (SELECT p50 FROM search_adr)) AS p50,
          COALESCE((SELECT p75 FROM quote_adr), (SELECT p75 FROM search_adr)) AS p75
        """,
        [market_id, market_id],
    ).fetchone()
    adr, adr_p25, adr_p50, adr_p75 = adr_row

    # Occupancy from historical night resolution (source of truth once daily scrapes accumulate).
    # Fallback: forward calendar blocked share only when no past history exists yet.
    occ_row = con.execute(
        """
        WITH hist AS (
          SELECT h.room_id, h.night, h.status
          FROM listing_night_history h
          JOIN listing_markets lm ON h.room_id = lm.room_id
          WHERE lm.market_id = ?
            AND h.night >= ? - INTERVAL '365 days'
            AND h.night < ?
            AND h.status IN ('occupied_inferred', 'vacant')
        ),
        hist_agg AS (
          SELECT
            CASE WHEN COUNT(*) > 0
                 THEN COUNT(*) FILTER (WHERE status = 'occupied_inferred') * 1.0 / COUNT(*)
            END AS occupancy_est,
            COUNT(DISTINCT night) AS window_days
          FROM hist
        ),
        forward AS (
          SELECT
            SUM(CASE WHEN available = FALSE THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0) AS blocked_pct,
            COUNT(*) AS fwd_nights
          FROM calendars c
          JOIN listing_markets lm ON c.room_id = lm.room_id
          WHERE lm.market_id = ?
            AND c.night >= current_date
            AND c.night < current_date + INTERVAL '30 days'
        )
        SELECT
          COALESCE((SELECT occupancy_est FROM hist_agg), (SELECT blocked_pct FROM forward)) AS occupancy_est,
          CASE
            WHEN (SELECT occupancy_est FROM hist_agg) IS NOT NULL THEN (SELECT window_days FROM hist_agg)
            ELSE LEAST(30, COALESCE((SELECT fwd_nights FROM forward), 0))
          END AS window_days,
          CASE WHEN (SELECT occupancy_est FROM hist_agg) IS NULL THEN TRUE ELSE FALSE END AS used_forward
        """,
        [market_id, as_of, as_of, market_id],
    ).fetchone()
    occupancy_est, window_days, used_forward = occ_row
    window_days = int(window_days or 0)
    is_partial = bool(used_forward) or window_days < 30

    revpar = (adr * occupancy_est) if adr is not None and occupancy_est is not None else None
    revenue_mo = (adr * occupancy_est * 30) if adr is not None and occupancy_est is not None else None
    revenue_year = (adr * occupancy_est * 365) if adr is not None and occupancy_est is not None else None

    # MoM supply / revenue
    prev = con.execute(
        """
        SELECT active_listings_live, revenue_mo
        FROM market_kpi_daily
        WHERE market_id = ? AND as_of = ? - INTERVAL '30 days'
        """,
        [market_id, as_of],
    ).fetchone()
    supply_mom = None
    revenue_mom = None
    if prev:
        prev_live, prev_rev = prev
        if prev_live and prev_live > 0 and active_live is not None:
            supply_mom = (active_live - prev_live) / prev_live
        if prev_rev and prev_rev > 0 and revenue_mo is not None:
            revenue_mom = (revenue_mo - prev_rev) / prev_rev

    # Professional host %
    prof = con.execute(
        """
        WITH live AS (
          SELECT l.host_id
          FROM listings l
          JOIN listing_markets lm ON l.room_id = lm.room_id
          WHERE lm.market_id = ?
            AND l.last_seen >= current_timestamp - INTERVAL '14 days'
            AND l.host_id IS NOT NULL
        ),
        host_counts AS (
          SELECT host_id, COUNT(*) AS cnt FROM live GROUP BY host_id
        )
        SELECT
          CASE WHEN SUM(cnt) > 0
               THEN SUM(CASE WHEN cnt >= 3 THEN cnt ELSE 0 END) * 1.0 / SUM(cnt)
               ELSE NULL END
        FROM host_counts
        """,
        [market_id],
    ).fetchone()[0]

    # Guest origin
    top_origin = con.execute(
        """
        SELECT guest_country
        FROM review_guests rg
        JOIN listing_markets lm ON rg.room_id = lm.room_id
        WHERE lm.market_id = ?
          AND guest_country IS NOT NULL AND guest_country <> ''
        GROUP BY guest_country
        ORDER BY COUNT(*) DESC
        LIMIT 1
        """,
        [market_id],
    ).fetchone()
    top_guest_origin = top_origin[0] if top_origin else None

    intl = con.execute(
        """
        SELECT
          CASE WHEN COUNT(*) FILTER (WHERE guest_country IS NOT NULL AND guest_country <> '') > 0
               THEN COUNT(*) FILTER (
                      WHERE guest_country IS NOT NULL
                        AND guest_country <> ''
                        AND lower(guest_country) NOT IN ('india', 'in')
                    ) * 1.0
                    / COUNT(*) FILTER (WHERE guest_country IS NOT NULL AND guest_country <> '')
               ELSE NULL END
        FROM review_guests rg
        JOIN listing_markets lm ON rg.room_id = lm.room_id
        WHERE lm.market_id = ?
        """,
        [market_id],
    ).fetchone()[0]

    con.execute(
        """
        INSERT INTO market_kpi_daily (
          as_of, market_id, active_listings_ttm, active_listings_live,
          adr, adr_p25, adr_p50, adr_p75, occupancy_est, revpar,
          revenue_mo, revenue_year, supply_mom, revenue_mom,
          professional_host_pct, top_guest_origin, intl_guest_pct,
          window_days, is_partial
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (as_of, market_id) DO UPDATE SET
          active_listings_ttm = excluded.active_listings_ttm,
          active_listings_live = excluded.active_listings_live,
          adr = excluded.adr,
          adr_p25 = excluded.adr_p25,
          adr_p50 = excluded.adr_p50,
          adr_p75 = excluded.adr_p75,
          occupancy_est = excluded.occupancy_est,
          revpar = excluded.revpar,
          revenue_mo = excluded.revenue_mo,
          revenue_year = excluded.revenue_year,
          supply_mom = excluded.supply_mom,
          revenue_mom = excluded.revenue_mom,
          professional_host_pct = excluded.professional_host_pct,
          top_guest_origin = excluded.top_guest_origin,
          intl_guest_pct = excluded.intl_guest_pct,
          window_days = excluded.window_days,
          is_partial = excluded.is_partial
        """,
        [
            as_of,
            market_id,
            active_ttm,
            active_live,
            adr,
            adr_p25,
            adr_p50,
            adr_p75,
            occupancy_est,
            revpar,
            revenue_mo,
            revenue_year,
            supply_mom,
            revenue_mom,
            prof,
            top_guest_origin,
            intl,
            window_days if window_days else None,
            is_partial,
        ],
    )

    # By bedrooms
    bed_rows = con.execute(
        """
        WITH base AS (
          SELECT l.room_id, COALESCE(l.bedrooms, -1) AS bedrooms
          FROM listings l
          JOIN listing_markets lm ON l.room_id = lm.room_id
          WHERE lm.market_id = ?
            AND l.last_seen >= current_timestamp - INTERVAL '14 days'
        ),
        adr_by AS (
          SELECT b.bedrooms, AVG(s.search_price) AS adr
          FROM base b
          JOIN listing_search_snapshots s ON s.room_id = b.room_id AND s.market_id = ?
          WHERE s.as_of >= current_timestamp - INTERVAL '30 days' AND s.search_price > 0
          GROUP BY b.bedrooms
        ),
        occ_by AS (
          SELECT b.bedrooms,
                 SUM(CASE WHEN c.available = FALSE THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0) AS occ
          FROM base b
          JOIN calendars c ON c.room_id = b.room_id
          WHERE c.night >= current_date - INTERVAL '365 days' AND c.night < current_date
          GROUP BY b.bedrooms
        )
        SELECT b.bedrooms, COUNT(*) AS listing_count, a.adr, o.occ
        FROM base b
        LEFT JOIN adr_by a ON b.bedrooms = a.bedrooms
        LEFT JOIN occ_by o ON b.bedrooms = o.bedrooms
        GROUP BY b.bedrooms, a.adr, o.occ
        """,
        [market_id, market_id],
    ).fetchall()

    for bedrooms, listing_count, b_adr, b_occ in bed_rows:
        if bedrooms is None or bedrooms < 0:
            continue
        b_revpar = (b_adr * b_occ) if b_adr is not None and b_occ is not None else None
        b_rev_mo = (b_adr * b_occ * 30) if b_adr is not None and b_occ is not None else None
        b_rev_yr = (b_adr * b_occ * 365) if b_adr is not None and b_occ is not None else None
        con.execute(
            """
            INSERT INTO market_kpi_by_bedrooms (
              as_of, market_id, bedrooms, listing_count, adr, occupancy_est, revpar, revenue_mo, revenue_year
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (as_of, market_id, bedrooms) DO UPDATE SET
              listing_count = excluded.listing_count,
              adr = excluded.adr,
              occupancy_est = excluded.occupancy_est,
              revpar = excluded.revpar,
              revenue_mo = excluded.revenue_mo,
              revenue_year = excluded.revenue_year
            """,
            [as_of, market_id, bedrooms, listing_count, b_adr, b_occ, b_revpar, b_rev_mo, b_rev_yr],
        )

    # By property type
    type_rows = con.execute(
        """
        WITH base AS (
          SELECT l.room_id, COALESCE(l.property_type, 'unknown') AS property_type
          FROM listings l
          JOIN listing_markets lm ON l.room_id = lm.room_id
          WHERE lm.market_id = ?
            AND l.last_seen >= current_timestamp - INTERVAL '14 days'
        ),
        adr_by AS (
          SELECT b.property_type, AVG(s.search_price) AS adr
          FROM base b
          JOIN listing_search_snapshots s ON s.room_id = b.room_id AND s.market_id = ?
          WHERE s.as_of >= current_timestamp - INTERVAL '30 days' AND s.search_price > 0
          GROUP BY b.property_type
        ),
        occ_by AS (
          SELECT b.property_type,
                 SUM(CASE WHEN c.available = FALSE THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0) AS occ
          FROM base b
          JOIN calendars c ON c.room_id = b.room_id
          WHERE c.night >= current_date - INTERVAL '365 days' AND c.night < current_date
          GROUP BY b.property_type
        )
        SELECT b.property_type, COUNT(*) AS listing_count, a.adr, o.occ
        FROM base b
        LEFT JOIN adr_by a ON b.property_type = a.property_type
        LEFT JOIN occ_by o ON b.property_type = o.property_type
        GROUP BY b.property_type, a.adr, o.occ
        """,
        [market_id, market_id],
    ).fetchall()

    for property_type, listing_count, t_adr, t_occ in type_rows:
        t_revpar = (t_adr * t_occ) if t_adr is not None and t_occ is not None else None
        t_rev_mo = (t_adr * t_occ * 30) if t_adr is not None and t_occ is not None else None
        con.execute(
            """
            INSERT INTO market_kpi_by_property_type (
              as_of, market_id, property_type, listing_count, adr, occupancy_est, revpar, revenue_mo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (as_of, market_id, property_type) DO UPDATE SET
              listing_count = excluded.listing_count,
              adr = excluded.adr,
              occupancy_est = excluded.occupancy_est,
              revpar = excluded.revpar,
              revenue_mo = excluded.revenue_mo
            """,
            [as_of, market_id, property_type, listing_count, t_adr, t_occ, t_revpar, t_rev_mo],
        )

    # Seasonality by month
    con.execute(
        """
        INSERT INTO market_seasonality (market_id, year_month, occupancy_est, adr, listing_nights)
        SELECT
          ? AS market_id,
          strftime(c.night, '%Y-%m') AS year_month,
          SUM(CASE WHEN c.available = FALSE THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0) AS occupancy_est,
          AVG(COALESCE(c.price, s.search_price)) AS adr,
          COUNT(*) AS listing_nights
        FROM calendars c
        JOIN listing_markets lm ON c.room_id = lm.room_id
        LEFT JOIN (
          SELECT room_id, AVG(search_price) AS search_price
          FROM listing_search_snapshots
          WHERE market_id = ?
          GROUP BY room_id
        ) s ON c.room_id = s.room_id
        WHERE lm.market_id = ?
        GROUP BY strftime(c.night, '%Y-%m')
        ON CONFLICT (market_id, year_month) DO UPDATE SET
          occupancy_est = excluded.occupancy_est,
          adr = excluded.adr,
          listing_nights = excluded.listing_nights
        """,
        [market_id, market_id, market_id],
    )

    # Forward 30 / 90
    for horizon in (30, 90):
        fwd = con.execute(
            f"""
            SELECT
              SUM(CASE WHEN available = FALSE THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0),
              SUM(CASE WHEN available = TRUE THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0)
            FROM calendars c
            JOIN listing_markets lm ON c.room_id = lm.room_id
            WHERE lm.market_id = ?
              AND c.night >= current_date
              AND c.night < current_date + INTERVAL '{horizon} days'
            """,
            [market_id],
        ).fetchone()
        blocked_pct, available_pct = fwd
        con.execute(
            """
            INSERT INTO market_forward (as_of, market_id, horizon_days, blocked_pct, available_pct)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (as_of, market_id, horizon_days) DO UPDATE SET
              blocked_pct = excluded.blocked_pct,
              available_pct = excluded.available_pct
            """,
            [as_of, market_id, horizon, blocked_pct, available_pct],
        )

    # Market score
    reg = con.execute(
        "SELECT regulation FROM markets WHERE market_id = ?", [market_id]
    ).fetchone()
    penalty = REGULATION_PENALTY.get((reg or ["Low"])[0], 0.0)

    # Normalize components crudely within single-market context using absolute scales
    occ_c = float(occupancy_est or 0)
    adr_c = min(float(adr or 0) / 10000.0, 1.0)  # INR scale heuristic
    rev_c = min(float(revenue_mo or 0) / 200000.0, 1.0)
    score = max(0.0, (0.4 * occ_c + 0.3 * adr_c + 0.3 * rev_c) - penalty)

    con.execute(
        """
        INSERT INTO market_scores (
          as_of, market_id, score, occ_component, adr_component, revenue_component, regulation_penalty
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (as_of, market_id) DO UPDATE SET
          score = excluded.score,
          occ_component = excluded.occ_component,
          adr_component = excluded.adr_component,
          revenue_component = excluded.revenue_component,
          regulation_penalty = excluded.regulation_penalty
        """,
        [as_of, market_id, score, occ_c, adr_c, rev_c, penalty],
    )

    return 1
