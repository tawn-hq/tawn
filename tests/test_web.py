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


def test_api_status_reports_home_and_db(db_engine, tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    client = TestClient(create_app(db_engine))
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert "initialized" in resp.json()


def test_api_domains_lists_enabled_domains(db_engine, tawn_home):
    # /api/domains lists every entry_points-discovered domain, marking
    # nav=True for names present in domains.yaml's `enabled` list — mirrors
    # the sibling test_api_wealth_latest_returns_state's setup pattern
    # rather than mocking the registry's internals directly.
    import yaml

    tawn_home.mkdir(parents=True, exist_ok=True)
    (tawn_home / "domains.yaml").write_text(yaml.safe_dump({"enabled": ["wealth"]}))

    client = TestClient(create_app(db_engine))
    resp = client.get("/api/domains")
    assert resp.status_code == 200
    body = resp.json()
    by_name = {d["name"]: d for d in body}
    assert by_name["wealth"] == {"name": "wealth", "label": "Wealth", "nav": True}
    assert all(d["nav"] is False for name, d in by_name.items() if name != "wealth")


def test_api_wealth_latest_returns_state(db_engine, tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    import yaml

    (tawn_home / "domains.yaml").write_text(yaml.safe_dump({"enabled": ["wealth"]}))
    _seed(db_engine)
    import tawn.domains.wealth.api as wealth_api_mod

    orig_make_engine = wealth_api_mod.make_engine
    wealth_api_mod.make_engine = lambda url=None: db_engine
    try:
        client = TestClient(create_app(db_engine))
        resp = client.get("/api/wealth/latest")
        assert resp.status_code == 200
        assert resp.json()["total_ngn"] == "25000"
    finally:
        wealth_api_mod.make_engine = orig_make_engine
