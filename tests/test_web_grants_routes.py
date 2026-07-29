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


def test_put_grants_writes_but_does_not_confirm(tawn_home):
    """Saving over HTTP writes the file and leaves it *unacknowledged*.

    This handler used to call `integrity_confirm` on its own write, which made
    the tamper-evident sidecar prove nothing: an edit from anywhere looked
    exactly as authentic as one made on the machine. The acknowledgement now
    has to come from `tawn grant confirm`, which the network cannot reach.
    """
    import pytest
    import yaml

    from tawn.capability.grants import load_verified
    from tawn.capability.integrity import IntegrityError
    from tawn.cli import init as cli_init

    cli_init()
    payload = {
        "read": [str(tawn_home)],
        "write": [],
        "observe": [],
        "mcp": [],
    }
    resp = _client().put("/api/grants", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["confirmed"] is False
    assert "tawn grant confirm" in body["message"]

    # The content landed…
    saved = yaml.safe_load((tawn_home / "grants.yaml").read_text())
    assert saved["read"] == [str(tawn_home.resolve())]

    # …but is not trusted until acknowledged locally.
    with pytest.raises(IntegrityError):
        load_verified(tawn_home / "grants.yaml")

    audit = (tawn_home / "audit.jsonl").read_text()
    assert "grant.edit" in audit
    assert "unconfirmed" in audit


def test_grants_become_active_after_a_local_confirm(tawn_home):
    """The intended flow end to end: edit from the browser, acknowledge from
    the machine."""
    from tawn.capability.grants import load_verified
    from tawn.capability.integrity import confirm
    from tawn.cli import init as cli_init

    cli_init()
    _client().put("/api/grants", json={"read": [str(tawn_home)], "write": [],
                                       "observe": [], "mcp": []})
    confirm(tawn_home / "grants.yaml")  # what `tawn grant confirm` does

    grants = load_verified(tawn_home / "grants.yaml")
    assert grants.read == [tawn_home.resolve()]


def test_get_audit_returns_entries(tawn_home):
    from tawn.cli import init as cli_init

    cli_init()
    resp = _client().get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data and "total" in data
    assert isinstance(data["entries"], list)
