"""Backfill group_key / ChunkGroup for chunks compiled before grouping existed."""

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.compiler.regroup import backfill_groups, ungrouped_count
from tawn.memory.schema import Base, Chunk, ChunkGroup


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _chunk(s, path, idx, content="Some durable content about routing.", **kw):
    c = Chunk(
        source_path=path, chunk_index=idx, content=content,
        content_hash="h" * 16, asof=datetime.datetime.utcnow(),
        compiled_at=datetime.datetime.utcnow(), **kw,
    )
    s.add(c)
    s.flush()
    return c


def test_ungrouped_count(db, tmp_path):
    _chunk(db, "/a.md", 0)
    _chunk(db, "/b.md", 0, group_key="/b.md", group_label="b.md")
    db.commit()
    assert ungrouped_count(db) == 1


def test_backfill_sets_group_key_and_builds_rows(db, tmp_path):
    _chunk(db, str(tmp_path / "notes" / "a.md"), 0)
    _chunk(db, str(tmp_path / "notes" / "a.md"), 1)
    _chunk(db, str(tmp_path / "notes" / "b.md"), 0)
    db.commit()

    n = backfill_groups(db, tmp_path)
    db.commit()

    assert n == 3
    assert ungrouped_count(db) == 0
    groups = {g.group_key: g for g in db.query(ChunkGroup).all()}
    assert len(groups) == 2
    a_key = str(tmp_path / "notes" / "a.md")
    assert groups[a_key].chunk_count == 2
    assert groups[a_key].title == "a.md"


def test_backfill_rebuilds_missing_group_rows_for_grouped_chunks(db, tmp_path):
    """Chunks may carry a group_key while chunk_groups was purged."""
    p = str(tmp_path / "n.md")
    _chunk(db, p, 0, group_key=p, group_label="n.md")
    db.commit()
    assert db.query(ChunkGroup).count() == 0

    backfill_groups(db, tmp_path)
    db.commit()

    assert db.query(ChunkGroup).one().chunk_count == 1


def test_backfill_is_idempotent(db, tmp_path):
    _chunk(db, str(tmp_path / "a.md"), 0)
    db.commit()

    backfill_groups(db, tmp_path)
    db.commit()
    first = db.query(ChunkGroup).one().chunk_count

    backfill_groups(db, tmp_path)
    db.commit()
    assert db.query(ChunkGroup).count() == 1
    assert db.query(ChunkGroup).one().chunk_count == first


def test_backfill_carries_dominant_domain(db, tmp_path):
    p = str(tmp_path / "d.md")
    _chunk(db, p, 0, domain="work")
    _chunk(db, p, 1, domain="work")
    _chunk(db, p, 2, domain="research")
    db.commit()

    backfill_groups(db, tmp_path)
    db.commit()

    assert db.query(ChunkGroup).one().domain == "work"


# ── Domain backfill ───────────────────────────────────────────────────────────

def test_backfill_domains_classifies_null_rows(db, tmp_path, monkeypatch):
    """Rows stored before the classifier reached markdown keep domain NULL."""
    import tawn.compiler.regroup as rg

    src = tmp_path / "proj" / "notes.md"
    src.parent.mkdir(parents=True)
    src.write_text("Notes about the deployment pipeline.")
    _chunk(db, str(src), 0)
    db.commit()

    monkeypatch.setattr(rg, "classify", lambda path, content: "work")
    n = rg.backfill_domains(db, tmp_path)
    db.commit()

    assert n == 1
    assert db.query(Chunk).one().domain == "work"


def test_backfill_domains_leaves_genuinely_undecidable_null(db, tmp_path, monkeypatch):
    """A classifier that declines must not be overridden with a guess."""
    import tawn.compiler.regroup as rg

    src = tmp_path / "x.md"
    src.write_text("Ambiguous content.")
    _chunk(db, str(src), 0)
    db.commit()

    monkeypatch.setattr(rg, "classify", lambda path, content: None)
    assert rg.backfill_domains(db, tmp_path) == 0
    assert db.query(Chunk).one().domain is None


def test_backfill_domains_does_not_touch_existing_domains(db, tmp_path, monkeypatch):
    import tawn.compiler.regroup as rg

    src = tmp_path / "y.md"
    src.write_text("Already classified.")
    _chunk(db, str(src), 0, domain="wealth")
    db.commit()

    monkeypatch.setattr(rg, "classify", lambda path, content: "work")
    rg.backfill_domains(db, tmp_path)
    assert db.query(Chunk).one().domain == "wealth"


def test_backfill_domains_uses_stored_content_when_file_is_gone(db, tmp_path, monkeypatch):
    """Granted sources move or get deleted; the chunk text is still classifiable."""
    import tawn.compiler.regroup as rg

    _chunk(db, str(tmp_path / "vanished.md"), 0, content="Deployment pipeline notes.")
    db.commit()

    seen: dict = {}

    def _cls(path, content):
        seen["content"] = content
        return "work"

    monkeypatch.setattr(rg, "classify", _cls)
    rg.backfill_domains(db, tmp_path)
    assert "Deployment pipeline" in seen["content"]
