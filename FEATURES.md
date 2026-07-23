# Flairbnb functionality

## Scraper API

- Get Airbnb API key from the site
- Search all stay listings in a map bounding box (paginated)
- Search first page of stay listings in a map bounding box
- Search stay listings from a full Airbnb search URL
- Fetch live StaysSearch GraphQL hash
- Get listing details by room URL or room ID
- Get listing metadata from a room URL
- Get listing price for a date range
- Get listing reviews
- Get listing availability calendar
- Get markets config for a currency/locale
- Get place IDs (autocomplete) for a location query
- Search experiences by place ID
- Search experiences from free-text input (uses first autocomplete match)
- Get all listings for a host/user ID
- Get host profile details
- Parse proxy credentials into a proxy URL
- Read nested values from Airbnb JSON responses

## Warehouse pipeline (MotherDuck)

- Seed 20 India markets + regulation + India events calendar
- Discover listings via map search every sync (snapshots + listing upsert)
- Enrich details, calendars, sample price quotes (rate-limited caps)
- Compute market KPIs: Active listings TTM, ADR, occupancy est, RevPAR, revenue/mo, Supply↑, Revenue↑
- Bedroom / property-type breakdowns, seasonality, forward 30/90d demand proxy
- Host concentration, market scores, comp-set tables
- Tier C stubs: property price, LTR rent, yield, rent gap, properties for sale
- GitHub Actions cron every 6 hours (`flairbnb-sync`)

## HTTP API (no frontend)

- FastAPI read layer over MotherDuck (`flairbnb-api`, see [API.md](API.md))
- Market KPIs, listings, calendars, occupancy history, events, sync runs
- Ops: `POST /v1/sync/run` to queue pipeline stages
- Invest/Tier C endpoints return NULLs until external feeds
