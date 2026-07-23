"""Tests for federation merge step."""
import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.federation.schema import Base, FederationRecord
from tawn.federation.merge import merge_pending, ingest_file
from tawn.compiler.compiler import _SENTINEL


@pytest.fixture()
def db(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "tawn"
    (h / "raw" / "imports").mkdir(parents=True)
    (h / "federation" / "inbox").mkdir(parents=True)
    return h


def _make_record(db, source, path, status="pending"):
    r = FederationRecord(source=source, source_path=str(path),
                         fingerprint="deadbeef12345678", status=status)
    db.add(r)
    db.commit()
    return r


def test_merge_pending_creates_raw_file(home, db, tmp_path):
    src = tmp_path / "session.jsonl"
    src.write_text(json.dumps({"role": "user", "content": "test merge"}) + "\n")
    _make_record(db, "claude-code", src)

    result = merge_pending(home, db)
    assert result["merged"] >= 1

    # infer_project() derives a project name from the source file's parent
    # dir when no `cwd` metadata is present, so the .md file lands one level
    # deeper (raw/imports/claude-code/<project>/*.md) — search recursively
    # rather than asserting a flat layout.
    import_files = list((home / "raw" / "imports" / "claude-code").rglob("*.md"))
    assert len(import_files) == 1
    assert "test merge" in import_files[0].read_text()


def test_merge_pending_marks_merged(home, db, tmp_path):
    src = tmp_path / "session.jsonl"
    src.write_text(json.dumps({"role": "user", "content": "hello"}) + "\n")
    record = _make_record(db, "claude-code", src)

    merge_pending(home, db)

    db.refresh(record)
    assert record.status == "merged"
    assert record.merged_at is not None


def test_merge_pending_marks_failed_on_missing_file(home, db, tmp_path):
    _make_record(db, "claude-code", tmp_path / "nonexistent.jsonl")
    result = merge_pending(home, db)
    assert result["failed"] >= 1


def test_merge_pending_skips_non_pending(home, db, tmp_path):
    src = tmp_path / "session.jsonl"
    src.write_text(json.dumps({"role": "user", "content": "already done"}) + "\n")
    _make_record(db, "claude-code", src, status="merged")
    result = merge_pending(home, db)
    assert result["merged"] == 0


def test_merge_queues_compile(home, db, tmp_path):
    src = tmp_path / "session.jsonl"
    src.write_text(json.dumps({"role": "user", "content": "queue test"}) + "\n")
    _make_record(db, "claude-code", src)
    merge_pending(home, db)
    assert (home / _SENTINEL).exists()


def test_ingest_file_creates_record(home, db, tmp_path):
    src = tmp_path / "session.jsonl"
    src.write_text(json.dumps({"role": "user", "content": "new"}) + "\n")
    record = ingest_file(home, db, src, source="claude-code")
    assert record is not None
    assert record.status == "pending"
    assert record.fingerprint != ""


def test_ingest_file_skips_duplicate(home, db, tmp_path):
    src = tmp_path / "session.jsonl"
    src.write_text(json.dumps({"role": "user", "content": "dup"}) + "\n")
    r1 = ingest_file(home, db, src, source="claude-code")
    r2 = ingest_file(home, db, src, source="claude-code")
    assert r1 is not None
    assert r2 is None
