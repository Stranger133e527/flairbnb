"""CLI entry: flairbnb-sync / python -m flairbnb.pipeline.sync"""

from __future__ import annotations

import argparse
import os
import sys

from flairbnb.pipeline.discover import discover_all, discover_market
from flairbnb.pipeline.enrich import enrich_all, enrich_market
from flairbnb.pipeline.metrics import compute_metrics
from flairbnb.pipeline.seed import seed_markets
from flairbnb.pipeline.util import open_db


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Flairbnb warehouse sync (Airbnb → MotherDuck)")
    p.add_argument(
        "--stage",
        choices=["seed", "discover", "enrich", "metrics", "all"],
        default="all",
        help="Pipeline stage to run",
    )
    p.add_argument(
        "--markets",
        default="all",
        help="Comma-separated market ids, or 'all'",
    )
    p.add_argument(
        "--max-listings",
        type=int,
        default=None,
        help="Cap listings per market during discover (overrides env)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Parallel enrich workers (default SYNC_ENRICH_WORKERS or 4)",
    )
    return p


def resolve_markets(raw: str) -> list[str] | None:
    if raw.strip().lower() in ("", "all"):
        return None
    return [m.strip() for m in raw.split(",") if m.strip()]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    market_ids = resolve_markets(args.markets)
    if args.max_listings is not None:
        os.environ["SYNC_MAX_LISTINGS_PER_MARKET"] = str(args.max_listings)
    if args.workers is not None:
        os.environ["SYNC_ENRICH_WORKERS"] = str(args.workers)

    con = open_db()
    try:
        if args.stage in ("seed", "all"):
            n = seed_markets(con=con)
            print(f"seed: {n} rows")

        if args.stage in ("discover", "all"):
            if market_ids and len(market_ids) == 1:
                n = discover_market(market_ids[0], con=con, max_listings=args.max_listings)
                print(f"discover {market_ids[0]}: {n} listings")
            else:
                out = discover_all(market_ids, con=con)
                print(f"discover: {out}")

        if args.stage in ("enrich", "all"):
            # Parallel enrich opens its own connections; close shared con first
            con.close()
            con = None
            if market_ids and len(market_ids) == 1 and (args.workers or 1) <= 1:
                out = enrich_market(market_ids[0], con=None)
                print(f"enrich {market_ids[0]}: {out}")
            else:
                out = enrich_all(market_ids, con=None, workers=args.workers)
                print(f"enrich: {out}")
            con = open_db()

        if args.stage in ("metrics", "all"):
            n = compute_metrics(con=con)
            print(f"metrics: {n} markets")

        return 0
    except Exception as exc:
        print(f"sync failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if con is not None:
            con.close()


if __name__ == "__main__":
    raise SystemExit(main())
