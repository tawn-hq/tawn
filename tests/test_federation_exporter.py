"""Tests for the canonical exporter."""
import datetime
import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.memory.schema import Base as MemBase, Chunk, Entity
from tawn.federation.exporter import export


@pytest.fixture()
def db(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    MemBase.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "tawn"
    (h / "federation" / "exports").mkdir(parents=True)
    return h


def _seed(db):
    now = datetime.datetime.utcnow()
    c = Chunk(domain="work", source_path="raw/imports/claude-code/2026-07-22.md",
              chunk_index=0, content="pgvector explanation", content_hash="abc",
              priority_tier=2, asof=now, compiled_at=now)
    e = Entity(canonical="pgvector", domain="work", confidence="high",
               first_seen=now, last_updated=now)
    db.add_all([c, e])
    db.commit()


def test_export_jsonl(home, db):
    _seed(db)
    result = export(home, db, fmt="jsonl")
    assert result["ok"] is True
    out = Path(result["out"])
    jsonl = out / "export.jsonl"
    assert jsonl.exists()
    rows = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["content"] == "pgvector explanation"
    assert rows[0]["domain"] == "work"


def test_export_markdown(home, db):
    _seed(db)
    result = export(home, db, fmt="markdown")
    assert result["ok"] is True
    out = Path(result["out"])
    md_files = list(out.glob("*.md"))
    assert any("work" in f.name for f in md_files)


def test_export_both(home, db):
    _seed(db)
    result = export(home, db, fmt="both")
    assert result["ok"] is True
    out = Path(result["out"])
    assert (out / "export.jsonl").exists()
    assert any(out.glob("*.md"))


def test_export_files_chmod_600(home, db):
    _seed(db)
    result = export(home, db, fmt="jsonl")
    out = Path(result["out"])
    jsonl = out / "export.jsonl"
    import stat
    mode = jsonl.stat().st_mode & 0o777
    assert mode == 0o600


def test_export_empty_db(home, db):
    result = export(home, db, fmt="both")
    assert result["ok"] is True
    assert result["files"] == []
