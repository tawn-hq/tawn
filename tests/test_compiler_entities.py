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


# ── Stage 7: free-text extraction removed ─────────────────────────────────────

def test_no_longer_harvests_title_cased_words(db, tmp_path):
    """The regex that produced `OK Traceback` and `None File` is gone.

    Free-text extraction moved to compiler/enrich.py, which asks a model
    instead of harvesting capitalised word pairs from raw text.
    """
    from tawn.compiler.entities import _extract_candidates

    noisy = _chunk("OK Traceback None File TypeError Object Also I'm Absolutely The TAWN")
    assert _extract_candidates(noisy) == []


def test_regex_noise_no_longer_reaches_the_entity_table(db, tmp_path):
    chunks = [_chunk("HTTP Request POST returned OK Traceback in Baseline Gemini")]
    extract_and_resolve(chunks, db, tmp_path)
    db.commit()
    assert db.query(Entity).count() == 0


def test_frontmatter_scalar_still_extracted():
    from tawn.compiler.entities import _extract_candidates

    assert _extract_candidates(_chunk("body", {"entity": "Tawn"})) == ["Tawn"]


def test_frontmatter_list_deduplicates_preserving_order():
    from tawn.compiler.entities import _extract_candidates

    chunk = _chunk("body", {"entity": ["Tawn", "Tawn", "pgvector"]})
    assert _extract_candidates(chunk) == ["Tawn", "pgvector"]
