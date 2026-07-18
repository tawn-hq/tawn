import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from tawn.db import Snapshot, session
from tawn.web import create_app

STATE = {
    "total_ngn": "25000",
    "classes": {"ngx": {"value_ngn": "5000", "pct": "20"}},
    "positions": [],
    "price_source": "manual",
}


def _seed(engine):
    with session(engine) as s:
        s.add(
            Snapshot(
                domain="wealth",
                asof=datetime(2026, 7, 7, tzinfo=timezone.utc),
                state_json=json.dumps(STATE),
            )
        )
        s.commit()


def test_home_lists_domains(db_engine):
    _seed(db_engine)
    client = TestClient(create_app(db_engine))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "wealth" in resp.text
    assert "25000" in resp.text  # overview shows net worth line


def test_api_wealth_latest_returns_state(db_engine):
    _seed(db_engine)
    client = TestClient(create_app(db_engine))
    resp = client.get("/api/wealth/latest")
    assert resp.status_code == 200
    assert resp.json()["total_ngn"] == "25000"


def test_api_wealth_latest_404_when_empty(db_engine):
    client = TestClient(create_app(db_engine))
    assert client.get("/api/wealth/latest").status_code == 404


def test_wealth_page_serves_html_with_total(db_engine):
    _seed(db_engine)
    client = TestClient(create_app(db_engine))
    resp = client.get("/wealth")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "25000" in resp.text
    assert "tawn" in resp.text.lower()
