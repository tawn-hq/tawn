"""Tests for federation web API routes."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tawn.federation.schema import Base as FedBase
from tawn.memory.schema import Base as MemBase
import tawn.db as db_mod


@pytest.fixture()
def db_engine(tmp_path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FedBase.metadata.create_all(engine)
    MemBase.metadata.create_all(engine)
    return engine


@pytest.fixture()
def client(db_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("TAWN_HOME", str(tmp_path / "tawn"))
    monkeypatch.setenv("TAWN_AGENT_MEMORY_DIR", str(tmp_path / "claude-projects"))
    monkeypatch.setenv("TAWN_DETECT_PATH_CODEX", str(tmp_path / "codex-sessions"))
    monkeypatch.setenv("TAWN_DETECT_PATH_GEMINI_CLI", str(tmp_path / "gemini-tmp"))
    home = tmp_path / "tawn"
    (home / "raw" / "imports").mkdir(parents=True)
    (home / "federation" / "adapters").mkdir(parents=True)
    (home / "federation" / "exports").mkdir(parents=True)

    def _get_session():
        with Session(db_engine) as s:
            yield s

    from tawn.web.app import create_app
    app = create_app(db_engine)
    app.dependency_overrides[db_mod.get_session] = _get_session
    return TestClient(app)


def test_get_sources_empty(client):
    resp = client.get("/api/federation/sources")
    assert resp.status_code == 200
    assert resp.json() == []


def test_post_source(client):
    resp = client.post("/api/federation/sources", json={
        "name": "hermes", "path": "~/.hermes/", "format": "jsonl"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["name"] == "hermes"


def test_get_sources_after_add(client):
    client.post("/api/federation/sources", json={
        "name": "hermes", "path": "~/.hermes/", "format": "jsonl"
    })
    resp = client.get("/api/federation/sources")
    assert resp.status_code == 200
    sources = resp.json()
    assert any(s["name"] == "hermes" for s in sources)


def test_delete_source(client):
    client.post("/api/federation/sources", json={
        "name": "hermes", "path": "~/.hermes/", "format": "jsonl"
    })
    resp = client.delete("/api/federation/sources/hermes")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    resp2 = client.get("/api/federation/sources")
    assert not any(s["name"] == "hermes" for s in resp2.json())


def test_get_records_empty(client):
    resp = client.get("/api/federation/records")
    assert resp.status_code == 200
    assert resp.json() == []


def test_post_merge_empty(client):
    resp = client.post("/api/federation/merge")
    assert resp.status_code == 200
    data = resp.json()
    assert "merged" in data
    assert data["merged"] == 0


def test_get_export(client):
    resp = client.get("/api/export?format=both")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "format" in data
