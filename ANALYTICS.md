# Flairbnb analytics dictionary

How market KPIs are calculated. Frontend should read MotherDuck views and show `as_of`, `window_days`, and `is_partial`.

## Core market KPIs (`v_market_kpis`)

| Metric | Formula |
|--------|---------|
| **Active Listings (TTM)** | Distinct room_ids in market with `last_seen` within 365 days |
| **Active (live)** | Same with 14-day window |
| **ADR** | Avg nightly from `price_quotes` (30d), else search snapshot price |
| **ADR p25/p50/p75** | Quantiles of same rate sample |
| **Occupancy (est)** | Calendar: unavailable nights ÷ observed past nights (min 30 nights/listing). Host blocks inflate this. |
| **RevPAR** | ADR × occupancy |
| **Revenue/mo** | ADR × occupancy × 30 |
| **Revenue/year** | ADR × occupancy × 365 |
| **Supply ↑** | MoM change in live active listings |
| **Revenue ↑** | MoM change in revenue/mo |
| **Regulation** | Manual seed: Low / Moderate / High |
| **Professional host %** | Share of live listings on hosts with ≥3 listings |
| **Top Guest Origin** | Mode of `review_guests.guest_country` |
| **Intl Guests %** | Non-India reviews ÷ reviews with country |

## 2-bedroom invest view (`v_market_kpis_2bd`)

| Metric | Formula |
|--------|---------|
| **Revenue/year (2bd)** | Same as above filtered to bedrooms = 2 |
| **Property price (2bd)** | From `external_property_comps` (Tier C; NULL until fed) |
| **Yield** | revenue_year_2bd / property_price_2bd |
| **Rent gap/mo** | revenue_mo_2bd − ltr_rent_mo_2bd |

## P0 competitor-parity views

- `v_market_by_bedrooms` / `v_market_by_property_type` — ADR, occ, RevPAR by segment
- `v_market_seasonality` — monthly occ + ADR
- `v_market_forward_90d` — % blocked vs available next 30/90 days
- `v_market_scores` — composite explorer score (occ/ADR/revenue − regulation penalty)
- `v_host_concentration` — host supply share
- `v_comp_set_metrics` — tracked comps
- `v_market_events` — India festivals / monsoon / IPL overlays
- `v_listing_calendar_forward` — listing nights next 90 days
- `v_properties_for_sale` — Tier C sales + STR estimate join

## Occupancy (source of truth)

We scrape **~1 forward month** daily (not a full year).

1. Each day store `calendar_observations` (room_id, night, as_of, available)
2. If a night flips **available → unavailable** vs the previous scrape → `occupancy_events.became_unavailable` → status **`occupied_inferred`**
3. When that night becomes past:
   - `occupied_inferred` = counted occupied
   - still `available` when the night passed = `vacant`
   - never saw open = `always_blocked` (excluded from primary occupancy)
4. Until enough past history exists, KPIs fall back to forward 30d blocked share and set `is_partial=true`

Primary occupancy:
`occupied_inferred / (occupied_inferred + vacant)` over past nights in window.
