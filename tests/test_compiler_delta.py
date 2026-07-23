import time
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from tawn.memory.schema import Base
from tawn.compiler.delta import scan_raw, update_file_state, DeltaResult


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def raw_dir(tmp_path):
    d = tmp_path / "raw"
    for sub in ["identity", "vault", "agent-notes"]:
        (d / sub).mkdir(parents=True)
    return d


def test_new_file_detected(raw_dir, db):
    f = raw_dir / "agent-notes" / "2026-07-20.md"
    f.write_text("# New note\n\nSome content here.\n")
    result = scan_raw(raw_dir, db)
    assert f in result.new
    assert result.changed == []
    assert result.deleted == []


def test_unchanged_file_not_in_delta(raw_dir, db):
    f = raw_dir / "agent-notes" / "2026-07-20.md"
    f.write_text("Stable content\n")
    update_file_state(f, db)
    db.commit()
    result = scan_raw(raw_dir, db)
    assert f not in result.new
    assert f not in result.changed


def test_changed_file_detected(raw_dir, db):
    f = raw_dir / "vault" / "notes.md"
    f.write_text("Original content\n")
    update_file_state(f, db)
    db.commit()
    # Force new mtime by writing different content
    import os, time as _time
    _time.sleep(0.01)
    f.write_text("Modified content\n")
    os.utime(f, (f.stat().st_mtime + 1, f.stat().st_mtime + 1))
    result = scan_raw(raw_dir, db)
    assert f in result.changed


def test_deleted_file_detected(raw_dir, db):
    f = raw_dir / "identity" / "profile.md"
    f.write_text("I am a researcher.\n")
    update_file_state(f, db)
    db.commit()
    f.unlink()
    result = scan_raw(raw_dir, db)
    assert any(str(p) == str(f) for p in result.deleted)


def test_empty_raw_dir_returns_empty_delta(raw_dir, db):
    result = scan_raw(raw_dir, db)
    assert result.new == []
    assert result.changed == []
    assert result.deleted == []
