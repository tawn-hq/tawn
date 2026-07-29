"""Reassemble a group's chunks into one readable document."""

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.memory.document import reconstruct
from tawn.memory.schema import Base, Chunk, ChunkGroup


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _chunk(s, gkey, idx, content, path="/doc.md", **kw):
    s.add(Chunk(
        source_path=path, chunk_index=idx, content=content,
        content_hash="h" * 16, asof=datetime.datetime.utcnow(),
        compiled_at=datetime.datetime.utcnow(), group_key=gkey, **kw,
    ))
    s.flush()


def test_reconstructs_in_chunk_order(db):
    _chunk(db, "/doc.md", 2, "Third part.")
    _chunk(db, "/doc.md", 0, "# Title\n\nFirst part.")
    _chunk(db, "/doc.md", 1, "## Middle\n\nSecond part.")
    db.commit()

    doc = reconstruct(db, "/doc.md")

    body = doc["body"]
    assert body.index("First part") < body.index("Second part") < body.index("Third part")
    assert doc["chunk_count"] == 3


def test_unknown_group_returns_none(db):
    assert reconstruct(db, "/nope.md") is None


def test_carries_group_title_and_summary(db):
    db.add(ChunkGroup(group_key="/doc.md", title="The Doc", summary="What it says.", chunk_count=1))
    _chunk(db, "/doc.md", 0, "Body text.")
    db.commit()

    doc = reconstruct(db, "/doc.md")
    assert doc["title"] == "The Doc"
    assert doc["summary"] == "What it says."


def test_falls_back_to_filename_when_untitled(db):
    _chunk(db, "/some/path/README.md", 0, "Body.", path="/some/path/README.md")
    db.commit()
    assert reconstruct(db, "/some/path/README.md")["title"] == "README.md"


def test_reports_provenance_and_domain(db):
    _chunk(db, "/doc.md", 0, "a", domain="work")
    _chunk(db, "/doc.md", 1, "b", domain="work")
    db.commit()

    doc = reconstruct(db, "/doc.md")
    assert doc["source_paths"] == ["/doc.md"]
    assert doc["domain"] == "work"


def test_spans_multiple_sources_when_group_does(db):
    """A day-bucketed import splits on seams, so one group can span files."""
    _chunk(db, "/day.md#alpha", 0, "first", path="/day.md")
    _chunk(db, "/day.md#alpha", 1, "second", path="/other.md")
    db.commit()

    doc = reconstruct(db, "/day.md#alpha")
    assert doc["source_paths"] == ["/day.md", "/other.md"]


def test_marks_enrichment_state(db):
    _chunk(db, "/doc.md", 0, "a", summary="s", enriched_at=datetime.datetime.utcnow())
    _chunk(db, "/doc.md", 1, "b")
    db.commit()

    doc = reconstruct(db, "/doc.md")
    assert doc["enriched_chunks"] == 1
    assert doc["chunk_count"] == 2


def test_body_separates_chunks_readably(db):
    _chunk(db, "/doc.md", 0, "Para one.")
    _chunk(db, "/doc.md", 1, "Para two.")
    db.commit()

    body = reconstruct(db, "/doc.md")["body"]
    assert "Para one.\n\nPara two." in body
