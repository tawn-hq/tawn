import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession

from tawn.memory.schema import Base
from tawn.observer import review as rv
from tawn.observer.attribution import Attribution
from tawn.observer.sessions import close_session, current_session, record_event

T0 = datetime.datetime(2026, 7, 26, 14, 2, tzinfo=datetime.timezone.utc)


def _sess():
    e = create_engine("sqlite://")
    Base.metadata.create_all(e)
    return SASession(e)


def _home(tmp_path, write_dir="out"):
    (tmp_path / "grants.yaml").write_text(
        f"read: []\nwrite: [{tmp_path / write_dir}]\nobserve: [fs]\n"
    )
    (tmp_path / write_dir).mkdir(exist_ok=True)
    return tmp_path


def _seeded(s):
    record_event(
        s, "tawn", "/x/a.py", "modified",
        Attribution("agent:claude-code", "high", "session"), T0, 40, 3,
    )
    record_event(
        s, "tawn", "/x/b.py", "added", Attribution("human", "high", "git"), T0, 10, 0
    )
    record_event(
        s, "tawn", "/x/c.py", "modified",
        Attribution("agent:unknown", "low", "timing"), T0, 5, 1,
    )
    return close_session(s, current_session(s, "tawn"), T0, "commit")


def test_low_confidence_reads_as_likely_not_as_fact():
    s = _sess()
    sess = _seeded(s)
    events = rv._events(s, sess)
    summary = rv.attribution_summary(events)
    assert "1 agent:claude-code" in summary
    assert "1 human" in summary
    assert "likely" in summary  # the timing guess is hedged
    assert "1 agent:unknown," not in summary


def test_note_is_written_under_the_write_grant(tmp_path, monkeypatch):
    s = _sess()
    sess = _seeded(s)
    monkeypatch.setattr(rv, "_analyse", lambda *a, **k: "### What changed\nStuff.\n")
    out = rv.write_note(s, sess, _home(tmp_path))
    assert out.note_state == "written"
    p = tmp_path / "out" / "reviews" / "tawn" / "2026-07-26.md"
    assert p.exists()
    body = p.read_text()
    assert "agent:claude-code" in body
    assert "Stuff." in body


def test_second_session_the_same_day_appends(tmp_path, monkeypatch):
    s = _sess()
    monkeypatch.setattr(rv, "_analyse", lambda *a, **k: "### What changed\nOne.\n")
    rv.write_note(s, _seeded(s), _home(tmp_path))
    rv.write_note(s, _seeded(s), _home(tmp_path))
    p = tmp_path / "out" / "reviews" / "tawn" / "2026-07-26.md"
    assert p.read_text().count("## 14:02") == 2


def test_no_model_still_writes_the_facts(tmp_path, monkeypatch):
    s = _sess()
    sess = _seeded(s)

    def _boom(*a, **k):
        raise RuntimeError("no model available")

    monkeypatch.setattr(rv, "_analyse", _boom)
    out = rv.write_note(s, sess, _home(tmp_path))
    assert out.note_state == "unanalysed"
    body = (tmp_path / "out" / "reviews" / "tawn" / "2026-07-26.md").read_text()
    assert "3 files" in body
    assert "agent:claude-code" in body  # losing analysis must not lose record


def test_no_write_grant_degrades_without_raising(tmp_path):
    s = _sess()
    sess = _seeded(s)
    (tmp_path / "grants.yaml").write_text("read: []\nwrite: []\nobserve: [fs]\n")
    out = rv.write_note(s, sess, tmp_path)
    assert out.note_state == "pending_note"
    assert out.note_path is None
    assert rv.note_path_for(tmp_path, "tawn", T0.date()) is None


def test_attempts_are_bounded(tmp_path):
    s = _sess()
    sess = _seeded(s)
    (tmp_path / "grants.yaml").write_text("read: []\nwrite: []\nobserve: [fs]\n")
    for _ in range(rv.MAX_NOTE_ATTEMPTS + 2):
        rv.write_note(s, sess, tmp_path)
    assert sess.note_state == "failed"
    assert sess.note_attempts == rv.MAX_NOTE_ATTEMPTS


def test_process_pending_only_touches_pending_sessions(tmp_path, monkeypatch):
    s = _sess()
    _seeded(s)
    monkeypatch.setattr(rv, "_analyse", lambda *a, **k: "### What changed\nX.\n")
    assert rv.process_pending(s, _home(tmp_path)) == 1
    assert rv.process_pending(s, _home(tmp_path)) == 0
