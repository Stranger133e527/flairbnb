-- Frontend-facing views (run after 001_init.sql)

CREATE OR REPLACE VIEW v_listing_latest AS
SELECT
  l.room_id,
  l.title,
  l.name,
  l.latitude,
  l.longitude,
  l.geohash,
  l.property_type,
  l.bedrooms,
  l.beds,
  l.bathrooms,
  l.person_capacity,
  l.host_id,
  l.rating_value,
  l.review_count,
  l.is_superhost,
  l.photo_count,
  l.amenity_count,
  l.first_seen,
  l.last_seen,
  l.details_scraped_at,
  l.calendar_scraped_at,
  s.search_price AS last_search_price,
  s.currency AS last_search_currency,
  s.as_of AS last_search_as_of
FROM listings l
LEFT JOIN (
  SELECT room_id, search_price, currency, as_of
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY room_id ORDER BY as_of DESC) AS rn
    FROM listing_search_snapshots
  ) t
  WHERE rn = 1
) s ON l.room_id = s.room_id;

CREATE OR REPLACE VIEW v_market_kpis AS
SELECT
  m.market_id,
  m.name,
  m.state,
  m.regulation,
  k.as_of,
  k.active_listings_ttm,
  k.active_listings_live,
  k.adr,
  k.adr_p25,
  k.adr_p50,
  k.adr_p75,
  k.occupancy_est,
  k.revpar,
  k.revenue_mo,
  k.revenue_year,
  k.supply_mom AS supply_up,
  k.revenue_mom AS revenue_up,
  k.professional_host_pct,
  k.top_guest_origin,
  k.intl_guest_pct,
  k.window_days,
  k.is_partial,
  'calendar_unavailable_share' AS occupancy_method,
  'quotes_then_search' AS adr_method,
  'manual_seed' AS regulation_source
FROM markets m
LEFT JOIN (
  SELECT *
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY as_of DESC) AS rn
    FROM market_kpi_daily
  ) t
  WHERE rn = 1
) k ON m.market_id = k.market_id
WHERE m.active;

CREATE OR REPLACE VIEW v_market_kpis_2bd AS
SELECT
  m.market_id,
  m.name,
  m.regulation,
  b.as_of,
  b.listing_count,
  b.adr,
  b.occupancy_est,
  b.revpar,
  b.revenue_mo,
  b.revenue_year,
  p.property_price AS property_price_2bd,
  CASE WHEN p.property_price > 0 THEN b.revenue_year / p.property_price END AS yield,
  r.rent_mo AS ltr_rent_mo_2bd,
  CASE WHEN r.rent_mo IS NOT NULL THEN b.revenue_mo - r.rent_mo END AS rent_gap_mo,
  p.source AS property_price_source,
  r.source AS ltr_source
FROM markets m
LEFT JOIN (
  SELECT *
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY as_of DESC) AS rn
    FROM market_kpi_by_bedrooms
    WHERE bedrooms = 2
  ) t WHERE rn = 1
) b ON m.market_id = b.market_id
LEFT JOIN (
  SELECT *
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY as_of DESC) AS rn
    FROM external_property_comps
    WHERE bedrooms = 2
  ) t WHERE rn = 1
) p ON m.market_id = p.market_id
LEFT JOIN (
  SELECT *
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY as_of DESC) AS rn
    FROM external_ltr_rents
    WHERE bedrooms = 2
  ) t WHERE rn = 1
) r ON m.market_id = r.market_id
WHERE m.active;

CREATE OR REPLACE VIEW v_market_by_bedrooms AS
SELECT * FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY market_id, bedrooms ORDER BY as_of DESC) AS rn
  FROM market_kpi_by_bedrooms
) t WHERE rn = 1;

CREATE OR REPLACE VIEW v_market_by_property_type AS
SELECT * FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY market_id, property_type ORDER BY as_of DESC) AS rn
  FROM market_kpi_by_property_type
) t WHERE rn = 1;

CREATE OR REPLACE VIEW v_market_seasonality AS
SELECT * FROM market_seasonality;

CREATE OR REPLACE VIEW v_market_forward_90d AS
SELECT * FROM market_forward WHERE horizon_days IN (30, 90);

CREATE OR REPLACE VIEW v_market_scores AS
SELECT * FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY as_of DESC) AS rn
  FROM market_scores
) t WHERE rn = 1;

CREATE OR REPLACE VIEW v_market_trends AS
SELECT
  market_id,
  as_of,
  active_listings_live,
  supply_mom AS supply_up,
  revenue_mo,
  revenue_mom AS revenue_up
FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY as_of DESC) AS rn
  FROM market_kpi_daily
) t WHERE rn = 1;

CREATE OR REPLACE VIEW v_host_concentration AS
SELECT
  lm.market_id,
  l.host_id,
  COUNT(*) AS listing_count,
  COUNT(*) * 1.0 / SUM(COUNT(*)) OVER (PARTITION BY lm.market_id) AS supply_share
FROM listing_markets lm
JOIN listings l ON lm.room_id = l.room_id
WHERE l.host_id IS NOT NULL
  AND l.last_seen >= current_timestamp - INTERVAL '14 days'
GROUP BY lm.market_id, l.host_id;

CREATE OR REPLACE VIEW v_listing_calendar_forward AS
SELECT
  room_id,
  night,
  available,
  price,
  currency,
  scraped_at
FROM calendars
WHERE night >= current_date
  AND night < current_date + INTERVAL '90 days';

CREATE OR REPLACE VIEW v_properties_for_sale AS
SELECT
  s.*,
  m.name AS market_name,
  b.revenue_year AS est_revenue_year_2bd
FROM external_sale_listings s
JOIN markets m ON s.market_id = m.market_id
LEFT JOIN (
  SELECT *
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY as_of DESC) AS rn
    FROM market_kpi_by_bedrooms WHERE bedrooms = 2
  ) t WHERE rn = 1
) b ON s.market_id = b.market_id AND s.bedrooms = 2;

CREATE OR REPLACE VIEW v_comp_set_metrics AS
SELECT
  c.comp_set_id,
  c.name AS comp_set_name,
  c.market_id,
  m.room_id,
  l.title,
  l.bedrooms,
  l.rating_value,
  l.review_count,
  l.last_seen
FROM comp_sets c
JOIN comp_set_members m ON c.comp_set_id = m.comp_set_id
LEFT JOIN listings l ON m.room_id = l.room_id;

CREATE OR REPLACE VIEW v_market_events AS
SELECT * FROM market_events;
