-- Flairbnb warehouse schema (DuckDB / MotherDuck)

CREATE TABLE IF NOT EXISTS markets (
  market_id VARCHAR PRIMARY KEY,
  name VARCHAR NOT NULL,
  state VARCHAR,
  regulation VARCHAR NOT NULL, -- Low | Moderate | High
  regulation_notes VARCHAR,
  ne_lat DOUBLE,
  ne_lng DOUBLE,
  sw_lat DOUBLE,
  sw_lng DOUBLE,
  zoom INTEGER DEFAULT 12,
  active BOOLEAN DEFAULT TRUE,
  updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS listings (
  room_id BIGINT PRIMARY KEY,
  title VARCHAR,
  name VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  geohash VARCHAR,
  property_type VARCHAR,
  bedrooms INTEGER,
  beds INTEGER,
  bathrooms DOUBLE,
  person_capacity INTEGER,
  host_id VARCHAR,
  rating_value DOUBLE,
  review_count INTEGER,
  is_superhost BOOLEAN,
  photo_count INTEGER,
  amenity_count INTEGER,
  first_seen TIMESTAMP,
  last_seen TIMESTAMP,
  details_scraped_at TIMESTAMP,
  calendar_scraped_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS listing_markets (
  room_id BIGINT,
  market_id VARCHAR,
  PRIMARY KEY (room_id, market_id)
);

CREATE TABLE IF NOT EXISTS listing_search_snapshots (
  as_of TIMESTAMP,
  market_id VARCHAR,
  room_id BIGINT,
  search_price DOUBLE,
  currency VARCHAR,
  price_qualifier VARCHAR,
  rating_value DOUBLE,
  review_count INTEGER,
  latitude DOUBLE,
  longitude DOUBLE,
  title VARCHAR,
  badges VARCHAR, -- JSON array string
  PRIMARY KEY (as_of, market_id, room_id)
);

CREATE TABLE IF NOT EXISTS listing_details (
  room_id BIGINT PRIMARY KEY,
  scraped_at TIMESTAMP,
  host_id VARCHAR,
  bedrooms INTEGER,
  beds INTEGER,
  bathrooms DOUBLE,
  person_capacity INTEGER,
  property_type VARCHAR,
  rating_value DOUBLE,
  review_count INTEGER,
  is_superhost BOOLEAN,
  photo_count INTEGER,
  amenity_count INTEGER,
  amenities_json VARCHAR,
  raw_json VARCHAR
);

CREATE TABLE IF NOT EXISTS calendars (
  room_id BIGINT,
  night DATE,
  available BOOLEAN,
  price DOUBLE,
  currency VARCHAR,
  scraped_at TIMESTAMP,
  PRIMARY KEY (room_id, night)
);

CREATE TABLE IF NOT EXISTS price_quotes (
  room_id BIGINT,
  check_in DATE,
  check_out DATE,
  adults INTEGER,
  currency VARCHAR,
  total DOUBLE,
  nightly DOUBLE,
  scraped_at TIMESTAMP,
  PRIMARY KEY (room_id, check_in, check_out, adults)
);

CREATE TABLE IF NOT EXISTS reviews_meta (
  room_id BIGINT PRIMARY KEY,
  review_count INTEGER,
  rating_value DOUBLE,
  scraped_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_guests (
  room_id BIGINT,
  review_id VARCHAR,
  guest_country VARCHAR,
  guest_city VARCHAR,
  created_at TIMESTAMP,
  scraped_at TIMESTAMP,
  PRIMARY KEY (room_id, review_id)
);

CREATE TABLE IF NOT EXISTS hosts (
  host_id VARCHAR PRIMARY KEY,
  name VARCHAR,
  listing_count INTEGER,
  is_superhost BOOLEAN,
  scraped_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_runs (
  run_id VARCHAR PRIMARY KEY,
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  market_id VARCHAR,
  stage VARCHAR,
  status VARCHAR,
  rows_written INTEGER DEFAULT 0,
  error VARCHAR
);

CREATE TABLE IF NOT EXISTS market_kpi_daily (
  as_of DATE,
  market_id VARCHAR,
  active_listings_ttm BIGINT,
  active_listings_live BIGINT,
  adr DOUBLE,
  adr_p25 DOUBLE,
  adr_p50 DOUBLE,
  adr_p75 DOUBLE,
  occupancy_est DOUBLE,
  revpar DOUBLE,
  revenue_mo DOUBLE,
  revenue_year DOUBLE,
  supply_mom DOUBLE,
  revenue_mom DOUBLE,
  professional_host_pct DOUBLE,
  top_guest_origin VARCHAR,
  intl_guest_pct DOUBLE,
  window_days INTEGER,
  is_partial BOOLEAN,
  PRIMARY KEY (as_of, market_id)
);

CREATE TABLE IF NOT EXISTS market_kpi_by_bedrooms (
  as_of DATE,
  market_id VARCHAR,
  bedrooms INTEGER,
  listing_count BIGINT,
  adr DOUBLE,
  occupancy_est DOUBLE,
  revpar DOUBLE,
  revenue_mo DOUBLE,
  revenue_year DOUBLE,
  PRIMARY KEY (as_of, market_id, bedrooms)
);

CREATE TABLE IF NOT EXISTS market_kpi_by_property_type (
  as_of DATE,
  market_id VARCHAR,
  property_type VARCHAR,
  listing_count BIGINT,
  adr DOUBLE,
  occupancy_est DOUBLE,
  revpar DOUBLE,
  revenue_mo DOUBLE,
  PRIMARY KEY (as_of, market_id, property_type)
);

CREATE TABLE IF NOT EXISTS market_seasonality (
  market_id VARCHAR,
  year_month VARCHAR,
  occupancy_est DOUBLE,
  adr DOUBLE,
  listing_nights BIGINT,
  PRIMARY KEY (market_id, year_month)
);

CREATE TABLE IF NOT EXISTS market_forward (
  as_of DATE,
  market_id VARCHAR,
  horizon_days INTEGER,
  blocked_pct DOUBLE,
  available_pct DOUBLE,
  PRIMARY KEY (as_of, market_id, horizon_days)
);

CREATE TABLE IF NOT EXISTS market_scores (
  as_of DATE,
  market_id VARCHAR,
  score DOUBLE,
  occ_component DOUBLE,
  adr_component DOUBLE,
  revenue_component DOUBLE,
  regulation_penalty DOUBLE,
  PRIMARY KEY (as_of, market_id)
);

CREATE TABLE IF NOT EXISTS market_events (
  event_id VARCHAR,
  name VARCHAR,
  start_date DATE,
  end_date DATE,
  demand VARCHAR,
  market_id VARCHAR,
  PRIMARY KEY (event_id, market_id)
);

CREATE TABLE IF NOT EXISTS comp_sets (
  comp_set_id VARCHAR PRIMARY KEY,
  name VARCHAR,
  market_id VARCHAR,
  created_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS comp_set_members (
  comp_set_id VARCHAR,
  room_id BIGINT,
  PRIMARY KEY (comp_set_id, room_id)
);

-- Tier C external stubs (NULL until fed)
CREATE TABLE IF NOT EXISTS external_property_comps (
  market_id VARCHAR,
  bedrooms INTEGER,
  property_price DOUBLE,
  currency VARCHAR DEFAULT 'INR',
  source VARCHAR,
  as_of DATE,
  PRIMARY KEY (market_id, bedrooms, as_of)
);

CREATE TABLE IF NOT EXISTS external_ltr_rents (
  market_id VARCHAR,
  bedrooms INTEGER,
  rent_mo DOUBLE,
  currency VARCHAR DEFAULT 'INR',
  source VARCHAR,
  as_of DATE,
  PRIMARY KEY (market_id, bedrooms, as_of)
);

CREATE TABLE IF NOT EXISTS external_sale_listings (
  market_id VARCHAR,
  listing_ext_id VARCHAR,
  bedrooms INTEGER,
  asking_price DOUBLE,
  url VARCHAR,
  as_of DATE,
  source VARCHAR,
  PRIMARY KEY (market_id, listing_ext_id, as_of)
);

CREATE TABLE IF NOT EXISTS opex_defaults (
  market_id VARCHAR PRIMARY KEY,
  platform_fee_pct DOUBLE DEFAULT 0.15,
  cleaning_mo DOUBLE DEFAULT 0,
  utilities_mo DOUBLE DEFAULT 0,
  maintenance_pct DOUBLE DEFAULT 0.05,
  notes VARCHAR
);
