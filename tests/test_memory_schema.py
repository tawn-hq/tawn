import datetime
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from tawn.memory.schema import Chunk, ChunkGroup, Entity, EntityEdge, FileState, CompileLog, Base


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


# ── Stage 7: enrichment columns ───────────────────────────────────────────────

def test_chunk_has_enrichment_columns(engine):
    with Session(engine) as s:
        c = Chunk(
            source_path="/x.md", chunk_index=0, content="hi",
            content_hash="abc", asof=datetime.datetime.utcnow(),
            title="A title", summary="A summary",
            group_key="/x.md", group_label="x.md",
        )
        s.add(c)
        s.commit()
        got = s.query(Chunk).filter_by(source_path="/x.md").one()
        assert got.title == "A title"
        assert got.summary == "A summary"
        assert got.enriched_at is None
        assert got.enrich_attempts == 0
        assert got.group_key == "/x.md"
        assert got.group_label == "x.md"


def test_chunk_group_roundtrips(engine):
    with Session(engine) as s:
        s.add(ChunkGroup(
            group_key="/x.md", title="Session", summary="What happened",
            domain="work", chunk_count=3,
        ))
        s.commit()
        got = s.query(ChunkGroup).one()
        assert got.chunk_count == 3
        assert got.enriched_at is None
        assert got.enrich_attempts == 0


def test_entity_edge_has_weight(engine):
    with Session(engine) as s:
        a = Entity(canonical="A")
        b = Entity(canonical="B")
        s.add_all([a, b])
        s.flush()
        s.add(EntityEdge(from_entity_id=a.id, to_entity_id=b.id,
                         relation="co-occurs", weight=4))
        s.commit()
        assert s.query(EntityEdge).one().weight == 4


def test_entity_edge_weight_defaults_to_one(engine):
    with Session(engine) as s:
        a = Entity(canonical="A")
        b = Entity(canonical="B")
        s.add_all([a, b])
        s.flush()
        s.add(EntityEdge(from_entity_id=a.id, to_entity_id=b.id, relation="uses"))
        s.commit()
        assert s.query(EntityEdge).one().weight == 1
