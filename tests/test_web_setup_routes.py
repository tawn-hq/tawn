from fastapi import FastAPI
from fastapi.testclient import TestClient

from tawn.web.routes.setup import router


def _client():
    app = FastAPI()
    app.include_router(router, prefix="/api/setup")
    return TestClient(app)


def test_init_endpoint_creates_home(tawn_home):
    resp = _client().post("/api/setup/init")
    assert resp.status_code == 200
    assert (tawn_home / "raw").is_dir()


def test_models_endpoint_returns_catalog(tawn_home, monkeypatch):
    from tawn.model.providers.ollama import OllamaProvider

    monkeypatch.setattr(OllamaProvider, "installed_models", lambda self: [])
    resp = _client().get("/api/setup/models")
    assert resp.status_code == 200
    names = [row["name"] for row in resp.json()]
    assert "qwen2.5:7b" in names


def test_keys_get_never_returns_value(tawn_home, monkeypatch):
    import tawn.model.keys as keys_mod

    monkeypatch.setattr(keys_mod.keyring, "get_password", lambda svc, user: "sk-SECRET")
    resp = _client().get("/api/setup/keys/anthropic")
    assert resp.status_code == 200
    assert "sk-SECRET" not in resp.text
    assert resp.json()["status"] == "set (keyring)"


def test_keys_post_stores_and_verifies(tawn_home, monkeypatch):
    store: dict = {}
    import tawn.model.keys as keys_mod

    monkeypatch.setattr(
        keys_mod.keyring,
        "set_password",
        lambda svc, user, val: store.__setitem__((svc, user), val),
    )
    monkeypatch.setattr(
        keys_mod.keyring, "get_password", lambda svc, user: store.get((svc, user))
    )
    resp = _client().post("/api/setup/keys/anthropic", json={"key": "sk-test"})
    assert resp.status_code == 200
    assert store[("tawn", "anthropic")] == "sk-test"
