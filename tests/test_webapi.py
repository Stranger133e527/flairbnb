"""API tests against local DuckDB (no MotherDuck required)."""

from fastapi.testclient import TestClient

from flairbnb.db import connect, migrate
from flairbnb.pipeline.seed import seed_markets
from flairbnb.webapi.app import app
from flairbnb.webapi import deps


def test_health_and_markets(tmp_path, monkeypatch):
    db = tmp_path / "api.duckdb"
    monkeypatch.setenv("FLAIRBNB_DB_PATH", str(db))
    monkeypatch.delenv("motherduck_token", raising=False)
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)

    con = connect()
    migrate(con)
    seed_markets(con=con)
    con.close()

    # Force API deps to use same local DB
    def _local_con():
        c = connect()
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[deps.get_con] = _local_con
    client = TestClient(app)
    try:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["markets"] == 20

        r = client.get("/v1/markets")
        assert r.status_code == 200
        assert len(r.json()) == 20

        r = client.get("/v1/markets/mumbai")
        assert r.status_code == 200
        assert r.json()["regulation"] == "Low"

        r = client.get("/v1/analytics/overview")
        assert r.status_code == 200
        assert "counts" in r.json()

        r = client.get("/v1/events?market_id=candolim")
        assert r.status_code == 200
        assert len(r.json()) >= 1
    finally:
        app.dependency_overrides.clear()
