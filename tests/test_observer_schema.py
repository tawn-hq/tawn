import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.memory.schema import Base, ObservedEvent, ObserverSession


def _sess():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_event_belongs_to_session_and_stores_no_content():
    s = _sess()
    now = datetime.datetime.now(datetime.timezone.utc)
    sess = ObserverSession(project="tawn", started_at=now)
    s.add(sess)
    s.flush()
    ev = ObservedEvent(
        session_id=sess.id, project="tawn", path="/x/y.py", kind="modified",
        lines_added=10, lines_removed=2, actor="agent:claude-code",
        confidence="high", basis="session", ts=now,
    )
    s.add(ev)
    s.commit()
    assert s.query(ObservedEvent).one().actor == "agent:claude-code"
    # No content column exists — storing source would make Tawn a second copy.
    assert not hasattr(ObservedEvent, "content")


def test_session_defaults_are_open_and_unattempted():
    s = _sess()
    now = datetime.datetime.now(datetime.timezone.utc)
    sess = ObserverSession(project="tawn", started_at=now)
    s.add(sess)
    s.commit()
    assert sess.note_state == "open"
    assert sess.note_attempts == 0
    assert sess.event_count == 0
    assert sess.ended_at is None
