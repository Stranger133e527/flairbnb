-- P1 scrape-native analytics tables

CREATE TABLE IF NOT EXISTS market_listing_velocity (
  as_of DATE,
  market_id VARCHAR,
  new_listings_7d BIGINT,
  new_listings_30d BIGINT,
  active_live BIGINT,
  PRIMARY KEY (as_of, market_id)
);

CREATE TABLE IF NOT EXISTS amenity_premiums (
  as_of DATE,
  market_id VARCHAR,
  amenity VARCHAR,
  listings_with BIGINT,
  adr_with DOUBLE,
  adr_without DOUBLE,
  adr_lift DOUBLE,
  PRIMARY KEY (as_of, market_id, amenity)
);

CREATE OR REPLACE VIEW v_market_velocity AS
SELECT * FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY as_of DESC) AS rn
  FROM market_listing_velocity
) t WHERE rn = 1;

CREATE OR REPLACE VIEW v_amenity_premiums_latest AS
SELECT * FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY market_id, amenity ORDER BY as_of DESC) AS rn
  FROM amenity_premiums
) t WHERE rn = 1;
