import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession

from tawn.memory.schema import Base, ObservedEvent, ObserverSession
from tawn.observer.attribution import Attribution
from tawn.observer.config import ObserverConfig
from tawn.observer.sessions import (
    close_idle_sessions, close_session, current_session, record_event,
)

CFG = ObserverConfig()
ATTR = Attribution("human", "high", "git")
T0 = datetime.datetime(2026, 7, 26, 12, 0, tzinfo=datetime.timezone.utc)


def _sess():
    e = create_engine("sqlite://")
    Base.metadata.create_all(e)
    return SASession(e)


def test_first_event_opens_a_session():
    s = _sess()
    record_event(s, "tawn", "/x/a.py", "modified", ATTR, T0)
    assert current_session(s, "tawn").event_count == 1


def test_later_events_attach_to_the_same_session():
    s = _sess()
    record_event(s, "tawn", "/x/a.py", "modified", ATTR, T0)
    record_event(
        s, "tawn", "/x/b.py", "added", ATTR, T0 + datetime.timedelta(minutes=1)
    )
    assert s.query(ObserverSession).count() == 1
    assert current_session(s, "tawn").event_count == 2


def test_projects_do_not_share_a_session():
    s = _sess()
    record_event(s, "tawn", "/x/a.py", "modified", ATTR, T0)
    record_event(s, "notes", "/n/a.md", "modified", ATTR, T0)
    assert s.query(ObserverSession).count() == 2


def test_idle_closes_after_the_configured_window():
    s = _sess()
    record_event(s, "tawn", "/x/a.py", "modified", ATTR, T0)
    assert close_idle_sessions(s, CFG, T0 + datetime.timedelta(minutes=19)) == []
    closed = close_idle_sessions(s, CFG, T0 + datetime.timedelta(minutes=21))
    assert [c.closed_by for c in closed] == ["idle"]
    assert current_session(s, "tawn") is None


def test_idle_is_measured_from_the_last_event_not_the_first():
    s = _sess()
    record_event(s, "tawn", "/x/a.py", "modified", ATTR, T0)
    record_event(
        s, "tawn", "/x/b.py", "modified", ATTR, T0 + datetime.timedelta(minutes=15)
    )
    assert close_idle_sessions(s, CFG, T0 + datetime.timedelta(minutes=25)) == []


def test_closing_marks_pending_note_so_it_gets_retried():
    s = _sess()
    record_event(s, "tawn", "/x/a.py", "modified", ATTR, T0)
    closed = close_session(s, current_session(s, "tawn"), T0, "commit")
    assert closed.note_state == "pending_note"
    assert closed.ended_at is not None


def test_a_new_event_after_closure_opens_a_fresh_session():
    s = _sess()
    record_event(s, "tawn", "/x/a.py", "modified", ATTR, T0)
    close_session(s, current_session(s, "tawn"), T0, "commit")
    record_event(
        s, "tawn", "/x/c.py", "modified", ATTR, T0 + datetime.timedelta(hours=2)
    )
    assert s.query(ObserverSession).count() == 2
    assert current_session(s, "tawn").event_count == 1


def test_events_carry_their_attribution():
    s = _sess()
    record_event(
        s, "tawn", "/x/a.py", "modified",
        Attribution("agent:codex", "high", "session"), T0,
        lines_added=9, lines_removed=1,
    )
    ev = s.query(ObservedEvent).one()
    assert (ev.actor, ev.confidence, ev.basis) == ("agent:codex", "high", "session")
    assert (ev.lines_added, ev.lines_removed) == (9, 1)
