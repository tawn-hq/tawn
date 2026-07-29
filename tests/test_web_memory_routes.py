"""Tests for memory API routes."""

import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tawn.compiler.embedder import EmbedError
from tawn.memory.schema import Base, Chunk
import tawn.db as db_mod


@pytest.fixture()
def db_engine(tmp_path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def client(db_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("TAWN_HOME", str(tmp_path / "tawn_home"))
    home = tmp_path / "tawn_home"
    (home / "raw" / "agent-notes").mkdir(parents=True)
    (home / "wiki").mkdir()

    def _get_session():
        with Session(db_engine) as s:
            yield s

    from tawn.web.app import create_app
    app = create_app(db_engine)
    app.dependency_overrides[db_mod.get_session] = _get_session
    return TestClient(app)


def test_post_note(client):
    resp = client.post("/api/note", json={"payload": "Test note about pgvector."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "path" in data
    assert "compile_queued" in data


def test_post_note_empty_rejected(client):
    resp = client.post("/api/note", json={"payload": ""})
    assert resp.status_code == 422


@patch("tawn.memory.recall.embed_text", side_effect=EmbedError("no embed"))
def test_post_recall_empty(mock_embed, client):
    resp = client.post("/api/recall", json={"query": "anything"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "snippets"
    assert data["chunks"] == []


@patch("tawn.compiler.compiler.embed_texts", side_effect=EmbedError("no embed"))
def test_post_compile(mock_embed, client):
    resp = client.post("/api/compile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "files_processed" in data


def test_get_compile_status(client):
    resp = client.get("/api/compile/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "pending" in data
    assert "last_compiled" in data


def test_get_brief_domain(client):
    resp = client.get("/api/brief/work")
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "work"
    assert "chunk_count" in data
    assert "entity_count" in data
    assert "summary" in data
    assert "stale_chunk_count" in data
    assert "last_compiled" in data


def test_get_brief_star(client):
    resp = client.get("/api/brief/*")
    assert resp.status_code == 200
    assert resp.json()["domain"] == "*"


@patch("tawn.memory.recall.embed_text", side_effect=EmbedError("no embed"))
def test_post_recall_with_chunks(mock_embed, client, db_engine):
    with Session(db_engine) as s:
        s.add(Chunk(
            source_path="raw/notes/test.md",
            chunk_index=0,
            content="Tawn uses pgvector for semantic search.",
            content_hash="abc12345abcd1234",
            priority_tier=3,
            asof=datetime.datetime.utcnow(),
            stale=False,
        ))
        s.commit()
    resp = client.post("/api/recall", json={"query": "pgvector"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "snippets"
    assert len(data.get("chunks", [])) >= 1
