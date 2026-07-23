# Flairbnb API

Read API over MotherDuck (no frontend in this repo).

## Run locally

```bash
cp .env.example .env   # set motherduck_token
pip install -e ".[dev]"
flairbnb-api
# → http://127.0.0.1:8000/docs
```

## Main endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | DB ping + counts |
| GET | `/v1/markets` | Market list |
| GET | `/v1/markets/{id}` | Market metadata |
| GET | `/v1/kpis` | All market KPIs |
| GET | `/v1/markets/{id}/kpis` | One market KPIs |
| GET | `/v1/markets/{id}/kpis/2bd` | 2bd invest view (Tier C nullable) |
| GET | `/v1/markets/{id}/by-bedrooms` | Bedroom breakdown |
| GET | `/v1/markets/{id}/by-property-type` | Property type breakdown |
| GET | `/v1/markets/{id}/seasonality` | Monthly seasonality |
| GET | `/v1/markets/{id}/forward` | Forward demand 30/90d |
| GET | `/v1/markets/{id}/score` | Market score |
| GET | `/v1/markets/{id}/hosts` | Host concentration |
| GET | `/v1/markets/{id}/listings` | Listings in market |
| GET | `/v1/markets/{id}/velocity` | New listing velocity |
| GET | `/v1/markets/{id}/amenity-premiums` | Amenity ADR lift |
| GET | `/v1/listings/{room_id}` | Listing card |
| GET | `/v1/listings/{room_id}/calendar` | Forward calendar nights |
| GET | `/v1/listings/{room_id}/occupancy-history` | Resolved night statuses |
| GET | `/v1/events` | India events overlay |
| GET | `/v1/sync/runs` | Pipeline run log |
| GET | `/v1/analytics/overview` | Dashboard summary |
| GET | `/v1/invest/2bd` | All markets 2bd invest |
| GET | `/v1/properties-for-sale` | Tier C sales (empty until fed) |
| POST | `/v1/sync/run` | Queue seed/discover/enrich/metrics |

Interactive docs: `/docs`
