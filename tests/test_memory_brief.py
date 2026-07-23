"""Tests for brief() verb (Task 13)."""

import datetime
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tawn.memory.brief import brief
from tawn.memory.schema import Base, Chunk, Entity


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "tawn"
    (h / "wiki").mkdir(parents=True)
    os.environ["TAWN_HOME"] = str(h)
    yield h
    del os.environ["TAWN_HOME"]


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_brief_empty_domain(home, db):
    result = brief("work", home=home, session=db)
    assert result["domain"] == "work"
    assert result["chunk_count"] == 0
    assert result["entity_count"] == 0


def test_brief_counts_chunks(home, db):
    for i in range(3):
        db.add(Chunk(
            domain="work",
            source_path="raw/agent-notes/a.md",
            chunk_index=i,
            content=f"Content {i}",
            content_hash=f"hash{i:016d}"[:16],
            priority_tier=3,
            asof=datetime.datetime.utcnow(),
        ))
    db.commit()
    result = brief("work", home=home, session=db)
    assert result["chunk_count"] == 3


def test_brief_counts_entities(home, db):
    db.add(Entity(canonical="Tawn", domain="work"))
    db.add(Entity(canonical="pgvector", domain="work"))
    db.commit()
    result = brief("work", home=home, session=db)
    assert result["entity_count"] == 2


def test_brief_reads_wiki_summary(home, db):
    wiki_domain = home / "wiki" / "work"
    wiki_domain.mkdir()
    (wiki_domain / "index.md").write_text("# Work\n\nActive projects: Tawn.\n")
    result = brief("work", home=home, session=db)
    assert result["summary"] != ""
    assert "Tawn" in result["summary"] or "Active" in result["summary"]


def test_brief_includes_staleness_fields(home, db):
    result = brief("work", home=home, session=db)
    assert "stale_chunk_count" in result
    assert "last_compiled" in result
    assert "staleness_hours" in result


def test_brief_stale_count(home, db):
    db.add(Chunk(
        domain="work", source_path="raw/a.md", chunk_index=0,
        content="Fresh", content_hash="fresh0000000000000"[:16],
        priority_tier=3, asof=datetime.datetime.utcnow(), stale=False,
    ))
    db.add(Chunk(
        domain="work", source_path="raw/b.md", chunk_index=0,
        content="Stale", content_hash="stale0000000000000"[:16],
        priority_tier=3, asof=datetime.datetime.utcnow(), stale=True,
    ))
    db.commit()
    result = brief("work", home=home, session=db)
    assert result["stale_chunk_count"] == 1
    assert result["chunk_count"] == 2


def test_brief_optional_session(home):
    result = brief("work", home=home)
    assert result["domain"] == "work"
    assert result["chunk_count"] == 0
