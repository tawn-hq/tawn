"""Tests for note(), recall(), brief() verbs."""

import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tawn.compiler.embedder import EmbedError
from tawn.memory.schema import Base, Chunk


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "home"
    (h / "raw" / "agent-notes").mkdir(parents=True)
    (h / "wiki").mkdir()
    return h


# ── note() ────────────────────────────────────────────────────────────────────

def test_note_creates_file(home):
    from tawn.memory.note import note
    from pathlib import Path
    result = note("I learned about pgvector today.", home=home)
    p = Path(result["path"])
    assert p.exists()
    assert "pgvector" in p.read_text()
    assert result["ok"] is True
    assert "compile_queued" in result


def test_note_creates_separate_files_per_call(home):
    from tawn.memory.note import note
    from pathlib import Path
    r1 = note("First entry.", home=home)
    r2 = note("Second entry.", home=home)
    p1, p2 = Path(r1["path"]), Path(r2["path"])
    assert p1.exists() and p2.exists()
    assert "First entry" in p1.read_text()
    assert "Second entry" in p2.read_text()


def test_note_writes_sentinel(home):
    from tawn.memory.note import note
    note("Sentinel test.", home=home)
    assert (home / ".compile-requested").exists()


def test_note_writes_yaml_frontmatter(home):
    from tawn.memory.note import note
    from pathlib import Path
    result = note("test content", domain="work", confidence="high", home=home)
    text = Path(result["path"]).read_text()
    assert "domain: work" in text
    assert "confidence: high" in text
    assert "---" in text


def test_note_ttl_written(home):
    from tawn.memory.note import note
    from pathlib import Path
    result = note("expires soon", ttl_days=7, home=home)
    assert "ttl_days: 7" in Path(result["path"]).read_text()


# ── recall() ──────────────────────────────────────────────────────────────────

def _seed_chunk(session, content, domain=None):
    session.add(Chunk(
        domain=domain,
        source_path="raw/agent-notes/2026-07-20.md",
        chunk_index=0,
        content=content,
        content_hash="abc12345abcd1234",
        priority_tier=3,
        asof=datetime.datetime.utcnow(),
        stale=False,
    ))
    session.flush()


@patch("tawn.memory.recall.embed_text", side_effect=EmbedError("no embed"))
def test_recall_full_text_match(mock_embed, db, home):
    from tawn.memory.recall import recall
    _seed_chunk(db, "Tawn uses pgvector for embeddings.")
    result = recall("pgvector", home=home, session=db)
    assert isinstance(result, dict)
    assert result["format"] == "snippets"
    chunks = result.get("chunks", [])
    assert any("pgvector" in c["content"] for c in chunks)


@patch("tawn.memory.recall.embed_text", side_effect=EmbedError("no embed"))
def test_recall_returns_empty_for_no_match(mock_embed, db, home):
    from tawn.memory.recall import recall
    _seed_chunk(db, "Some unrelated text.")
    result = recall("xyzzy_impossible_match_99", home=home, session=db)
    assert result["chunks"] == []


@patch("tawn.memory.recall.embed_text", side_effect=EmbedError("no embed"))
def test_recall_domain_filter(mock_embed, db, home):
    from tawn.memory.recall import recall
    _seed_chunk(db, "Work note about pgvector.", domain="work")
    _seed_chunk(db, "Hobby note about pgvector.", domain="hobby")
    result = recall("pgvector", home=home, session=db, domain="work")
    assert isinstance(result, dict)
    chunks = result.get("chunks", [])
    assert all(c["domain"] == "work" for c in chunks)


@patch("tawn.memory.recall.embed_text", side_effect=EmbedError("no embed"))
def test_recall_respects_limit(mock_embed, db, home):
    from tawn.memory.recall import recall
    for i in range(10):
        db.add(Chunk(
            source_path=f"raw/agent-notes/note{i}.md",
            chunk_index=0,
            content=f"Keyword content item {i}",
            content_hash=f"hash{i:016d}"[:16],
            priority_tier=3,
            asof=datetime.datetime.utcnow(),
            stale=False,
        ))
    db.flush()
    result = recall("Keyword", home=home, session=db, top_k=3)
    assert isinstance(result, dict)
    assert len(result.get("chunks", [])) <= 3


@patch("tawn.memory.recall.embed_text", side_effect=EmbedError("no embed"))
def test_recall_composed_returns_answer_key(mock_embed, db, home):
    from tawn.memory.recall import recall
    _seed_chunk(db, "Tawn stores notes in raw/.")
    result = recall("Tawn", home=home, session=db, format="composed")
    assert isinstance(result, dict)
    assert result["format"] == "composed"
    assert "answer" in result


# ── brief() ───────────────────────────────────────────────────────────────────

def test_brief_returns_dict(db, home):
    from tawn.memory.brief import brief
    result = brief("work", home, db)
    assert isinstance(result, dict)
    assert "domain" in result
    assert "chunk_count" in result
    assert "entity_count" in result
    assert "summary" in result
    assert "stale_chunk_count" in result
    assert "last_compiled" in result


def test_brief_empty_domain(db, home):
    from tawn.memory.brief import brief
    result = brief("nonexistent", home, db)
    assert result["chunk_count"] == 0
    assert result["entity_count"] == 0


def test_brief_counts_chunks(db, home):
    from tawn.memory.brief import brief
    _seed_chunk(db, "Work note A.", domain="work")
    _seed_chunk(db, "Work note B.", domain="work")
    _seed_chunk(db, "Hobby note.", domain="hobby")
    result = brief("work", home, db)
    assert result["chunk_count"] == 2
    assert result["domain"] == "work"


def test_brief_star_domain_counts_all(db, home):
    from tawn.memory.brief import brief
    _seed_chunk(db, "Work note.", domain="work")
    _seed_chunk(db, "Hobby note.", domain="hobby")
    result = brief("*", home, db)
    assert result["chunk_count"] >= 2
