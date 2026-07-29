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


# ── Stage 7: review-queue is not memory ───────────────────────────────────────

def test_scan_raw_skips_review_queue(tmp_path):
    """The entity resolver's triage output must never be indexed as memory."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from tawn.memory.schema import Base
    from tawn.compiler.delta import scan_raw

    raw = tmp_path / "raw"
    (raw / "agent-notes").mkdir(parents=True)
    (raw / "agent-notes" / "real.md").write_text("A real durable note.")
    (raw / "review-queue").mkdir(parents=True)
    (raw / "review-queue" / "entity-conflicts.md").write_text(
        "## Ambiguous: 'OK Traceback'\nClose matches: None File\n"
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        result = scan_raw(raw, s)

    names = {p.name for p in result.new}
    assert "real.md" in names
    assert "entity-conflicts.md" not in names


def test_scan_raw_does_not_report_non_raw_files_as_deleted(tmp_path):
    """Regression: `known` was every FileState row, `disk_files` only raw/.

    Granted repos, history and agent memory therefore looked deleted on every
    compile, so their chunks were removed and re-added on alternating runs —
    one real compile added 1,347 chunks and the next removed 2,303.
    """
    import datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from tawn.compiler.delta import scan_raw
    from tawn.memory.schema import Base, FileState

    raw = tmp_path / "raw" / "notes"
    raw.mkdir(parents=True)
    kept = raw / "kept.md"
    kept.write_text("still here")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        now = datetime.datetime.utcnow()
        # Under raw/ and gone from disk → genuinely deleted.
        s.add(FileState(path=str(raw / "gone.md"), mtime=1.0, content_hash="a", compiled_at=now))
        # Outside raw/ → not scan_raw's business at all.
        s.add(FileState(path="/home/u/repo/README.md", mtime=1.0, content_hash="b", compiled_at=now))
        s.add(FileState(path=str(tmp_path / "history" / "s.jsonl"), mtime=1.0, content_hash="c", compiled_at=now))
        s.commit()

        result = scan_raw(tmp_path / "raw", s)

    deleted = {str(p) for p in result.deleted}
    assert str(raw / "gone.md") in deleted
    assert "/home/u/repo/README.md" not in deleted
    assert str(tmp_path / "history" / "s.jsonl") not in deleted
