-- Daily calendar observation history + resolved night status (source of truth for past occupancy)

CREATE TABLE IF NOT EXISTS calendar_observations (
  room_id BIGINT,
  night DATE,
  as_of DATE,
  available BOOLEAN,
  scraped_at TIMESTAMP,
  PRIMARY KEY (room_id, night, as_of)
);

-- Resolved status for nights we have watched (especially past nights)
-- status:
--   occupied_inferred  = saw available=true then later available=false (booking/block flip)
--   vacant             = night passed while last state was still available
--   always_blocked     = never saw available=true while watching
--   open_future        = night still in the future and currently available
--   blocked_future     = night still in the future and currently unavailable (no prior open sighting)
CREATE TABLE IF NOT EXISTS listing_night_history (
  room_id BIGINT,
  night DATE,
  status VARCHAR,
  became_unavailable_on DATE,
  last_available BOOLEAN,
  observation_count INTEGER,
  updated_at TIMESTAMP,
  PRIMARY KEY (room_id, night)
);

CREATE TABLE IF NOT EXISTS occupancy_events (
  room_id BIGINT,
  night DATE,
  detected_on DATE,
  event_type VARCHAR, -- became_unavailable
  prev_available BOOLEAN,
  curr_available BOOLEAN,
  PRIMARY KEY (room_id, night, detected_on, event_type)
);

CREATE OR REPLACE VIEW v_occupancy_history AS
SELECT
  h.room_id,
  h.night,
  h.status,
  h.became_unavailable_on,
  h.last_available,
  h.observation_count,
  h.updated_at,
  lm.market_id
FROM listing_night_history h
LEFT JOIN listing_markets lm ON h.room_id = lm.room_id;
