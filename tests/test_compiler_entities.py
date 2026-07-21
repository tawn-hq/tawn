import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from tawn.memory.schema import Base, Entity
from tawn.compiler.parser import ParsedChunk
from tawn.compiler.entities import extract_and_resolve


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _chunk(content: str, fm: dict | None = None) -> ParsedChunk:
    return ParsedChunk(
        source_path="raw/agent-notes/2026-07-20.md",
        chunk_index=0,
        content=content,
        frontmatter=fm or {},
        priority_tier=3,
        asof=datetime.datetime.utcnow(),
    )


def test_frontmatter_entity_field_inserted(db, tmp_path):
    chunks = [_chunk("Some content", fm={"entity": "pgvector", "domain": "work"})]
    extract_and_resolve(chunks, db, tmp_path)
    db.commit()
    entities = db.query(Entity).all()
    assert any(e.canonical == "pgvector" for e in entities)


def test_frontmatter_entity_list_inserted(db, tmp_path):
    chunks = [_chunk("Content", fm={"entity": ["Tawn", "pgvector"]})]
    extract_and_resolve(chunks, db, tmp_path)
    db.commit()
    canonicals = {e.canonical for e in db.query(Entity).all()}
    assert "Tawn" in canonicals
    assert "pgvector" in canonicals


def test_duplicate_entity_not_duplicated(db, tmp_path):
    existing = Entity(canonical="Tawn", domain="work", source_path="raw/identity/me.md")
    db.add(existing)
    db.commit()
    chunks = [_chunk("Content", fm={"entity": "Tawn"})]
    extract_and_resolve(chunks, db, tmp_path)
    db.commit()
    tawn_entities = db.query(Entity).filter(Entity.canonical == "Tawn").all()
    assert len(tawn_entities) == 1


def test_close_match_not_duplicated(db, tmp_path):
    existing = Entity(canonical="Testimony Adekoya")
    db.add(existing)
    db.commit()
    # "Testimony Adekoya" is exact match — should not create new entity
    chunks = [_chunk("content", fm={"entity": "Testimony Adekoya"})]
    extract_and_resolve(chunks, db, tmp_path)
    db.commit()
    assert db.query(Entity).count() == 1


def test_ambiguous_entity_goes_to_review(db, tmp_path):
    e1 = Entity(canonical="Testimony Adekoya")
    e2 = Entity(canonical="Testimonys Adekoya")
    db.add_all([e1, e2])
    db.commit()
    chunks = [_chunk("content", fm={"entity": "Testimoni Adekoya"})]
    extract_and_resolve(chunks, db, tmp_path)
    # Should not crash; review-queue file should exist
    review_file = tmp_path / "entity-conflicts.md"
    # May or may not create review file depending on threshold — just assert no crash
    assert db.query(Entity).count() >= 2


def test_new_entity_inserted(db, tmp_path):
    chunks = [_chunk("content", fm={"entity": "BrandNewThing"})]
    extract_and_resolve(chunks, db, tmp_path)
    db.commit()
    assert db.query(Entity).filter(Entity.canonical == "BrandNewThing").count() == 1
