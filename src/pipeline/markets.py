"""Load market and event config from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_MARKETS = _ROOT / "config" / "markets.yaml"
_EVENTS = _ROOT / "config" / "india_events.yaml"


def load_markets(path: Path | None = None) -> list[dict[str, Any]]:
    data = yaml.safe_load((path or _MARKETS).read_text(encoding="utf-8"))
    return list(data.get("markets") or [])


def get_market(market_id: str) -> dict[str, Any]:
    for m in load_markets():
        if m["id"] == market_id:
            return m
    raise KeyError(f"Unknown market_id: {market_id}")


def load_events(path: Path | None = None) -> list[dict[str, Any]]:
    data = yaml.safe_load((path or _EVENTS).read_text(encoding="utf-8"))
    return list(data.get("events") or [])


def expand_events_for_db(events: list[dict[str, Any]] | None = None, market_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Flatten events into (event_id, market_id) rows."""
    events = events or load_events()
    all_ids = market_ids or [m["id"] for m in load_markets()]
    rows: list[dict[str, Any]] = []
    for ev in events:
        targets = ev.get("markets") or ["all"]
        if targets == ["all"] or targets == "all":
            ids = all_ids
        else:
            ids = list(targets)
        for mid in ids:
            rows.append(
                {
                    "event_id": ev["id"],
                    "name": ev["name"],
                    "start_date": ev["start"],
                    "end_date": ev["end"],
                    "demand": ev.get("demand"),
                    "market_id": mid,
                }
            )
    return rows
