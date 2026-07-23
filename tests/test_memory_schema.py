import datetime
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from tawn.memory.schema import Chunk, Entity, EntityEdge, FileState, CompileLog, Base


@pytest.fixture()
def engine():
    e = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(e)
    return e


def test_chunk_table_exists(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'"))
        assert result.fetchone() is not None


def test_entity_table_exists(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='entities'"))
        assert result.fetchone() is not None


def test_file_state_table_exists(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='file_state'"))
        assert result.fetchone() is not None


def test_compile_log_table_exists(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='compile_log'"))
        assert result.fetchone() is not None


def test_insert_chunk(engine):
    with Session(engine) as s:
        chunk = Chunk(
            domain="work",
            source_path="raw/agent-notes/2026-07-20.md",
            chunk_index=0,
            content="Test content",
            content_hash="abc123",
            priority_tier=3,
            asof=datetime.datetime.utcnow(),
        )
        s.add(chunk)
        s.commit()
        assert chunk.id is not None


def test_insert_entity(engine):
    with Session(engine) as s:
        e = Entity(canonical="Tawn", domain="work", source_path="raw/identity/me.md")
        s.add(e)
        s.commit()
        assert e.id is not None


def test_entity_edge(engine):
    with Session(engine) as s:
        e1 = Entity(canonical="Tawn")
        e2 = Entity(canonical="pgvector")
        s.add_all([e1, e2])
        s.flush()
        edge = EntityEdge(from_entity_id=e1.id, to_entity_id=e2.id, relation="uses")
        s.add(edge)
        s.commit()
        assert edge.id is not None
