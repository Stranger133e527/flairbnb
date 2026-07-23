# Flairbnb

India short-term rental analytics warehouse. Scrapes Airbnb for 20 markets, stores metrics in MotherDuck, syncs every 6 hours via GitHub Actions. Frontend reads MotherDuck directly (no API).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# set motherduck_token=... from MotherDuck UI
```

Without a token, sync uses local `data/flairbnb.duckdb`.

## Sync

```bash
# Seed markets + India events
python -m flairbnb.pipeline.sync --stage seed

# Full pipeline
python -m flairbnb.pipeline.sync --stage all

# One market, capped discover
python -m flairbnb.pipeline.sync --stage discover --markets candolim --max-listings 50
```

## GitHub Actions

1. Repo secret `MOTHERDUCK_TOKEN`
2. Optional secret `FLAIRBNB_PROXY_URL`
3. Workflow [`.github/workflows/sync.yml`](.github/workflows/sync.yml) runs every 6 hours

## Docs

- [FEATURES.md](FEATURES.md) — capabilities
- [ANALYTICS.md](ANALYTICS.md) — KPI formulas
- [config/markets.yaml](config/markets.yaml) — 20 India markets
