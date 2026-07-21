from fastapi import FastAPI
from fastapi.testclient import TestClient

from tawn.web.routes.grants import router


def _client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_get_grants_returns_current_state(tawn_home):
    from tawn.cli import init as cli_init

    cli_init()
    resp = _client().get("/api/grants")
    assert resp.status_code == 200
    body = resp.json()
    assert body["read"] == [] and body["system"] is False


def test_put_grants_rewrites_and_reconfirms(tawn_home):
    from tawn.cli import init as cli_init

    cli_init()
    payload = {
        "read": [str(tawn_home)],
        "write": [],
        "observe": [],
        "system": False,
        "mcp": [],
    }
    resp = _client().put("/api/grants", json=payload)
    assert resp.status_code == 200

    from tawn.capability.grants import load_verified

    grants = load_verified(tawn_home / "grants.yaml")
    assert grants.read == [tawn_home.resolve()]

    audit = (tawn_home / "audit.log").read_text()
    assert "grant.edit" in audit


def test_get_audit_returns_entries(tawn_home):
    from tawn.cli import init as cli_init

    cli_init()
    resp = _client().get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data and "total" in data
    assert isinstance(data["entries"], list)
