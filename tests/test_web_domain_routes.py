from fastapi import FastAPI
from fastapi.testclient import TestClient

from tawn.web.routes.domains import router


def _client():
    app = FastAPI()
    app.include_router(router, prefix="/api/domains")
    return TestClient(app)


GENERATED = (
    "from tawn.domains.base import DomainSpec\n"
    "def register():\n"
    "    return DomainSpec(name='scratch', label='Scratch')\n"
)


def test_draft_generates_and_does_not_enable(tawn_home, monkeypatch):
    import tawn.web.routes.domains as domains_mod

    monkeypatch.setattr(domains_mod, "has_usable_model", lambda home: True)
    monkeypatch.setattr(
        domains_mod, "generate_domain_source", lambda description, router: GENERATED
    )
    resp = _client().post(
        "/api/domains/draft",
        json={"name": "scratch", "description": "a scratch domain"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "register()" in body["source"]

    import tawn.domains.registry as registry

    assert "scratch" not in registry.enabled_names(tawn_home)


def test_promote_writes_and_enables(tawn_home, monkeypatch):
    import tawn.web.routes.domains as domains_mod

    monkeypatch.setattr(domains_mod, "has_usable_model", lambda home: True)
    monkeypatch.setattr(
        domains_mod, "generate_domain_source", lambda description, router: GENERATED
    )
    _client().post(
        "/api/domains/draft",
        json={"name": "scratch", "description": "a scratch domain"},
    )
    resp = _client().post("/api/domains/draft/scratch/promote")
    assert resp.status_code == 200

    import tawn.domains.registry as registry

    assert "scratch" in registry.enabled_names(tawn_home)
    assert (tawn_home / "domains" / "scratch" / "domain.py").exists()


def test_discard_deletes_draft(tawn_home, monkeypatch):
    import tawn.web.routes.domains as domains_mod

    monkeypatch.setattr(domains_mod, "has_usable_model", lambda home: True)
    monkeypatch.setattr(
        domains_mod, "generate_domain_source", lambda description, router: GENERATED
    )
    _client().post("/api/domains/draft", json={"name": "scratch", "description": "x"})
    resp = _client().delete("/api/domains/draft/scratch")
    assert resp.status_code == 200
    assert not (tawn_home / "domains" / ".drafts" / "scratch").exists()
