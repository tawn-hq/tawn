"""Grouping observed events into work sessions.

A session is one project's window of contiguous activity. It closes on a
commit, on idle, or on an explicit review. `now` is always a parameter rather
than read from the clock, so idle behaviour is testable without sleeping.
"""

from __future__ import annotations

import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from tawn.memory.schema import ObservedEvent, ObserverSession
from tawn.observer.attribution import Attribution
from tawn.observer.config import ObserverConfig

OPEN = "open"
PENDING = "pending_note"


def current_session(session: Session, project: str) -> ObserverSession | None:
    return (
        session.query(ObserverSession)
        .filter(ObserverSession.project == project, ObserverSession.ended_at.is_(None))
        .order_by(ObserverSession.started_at.desc())
        .first()
    )


def open_session(
    session: Session, project: str, now: datetime.datetime
) -> ObserverSession:
    sess = ObserverSession(project=project, started_at=now, note_state=OPEN)
    session.add(sess)
    session.flush()
    return sess


def record_event(
    session: Session,
    project: str,
    path: str,
    kind: str,
    attr: Attribution,
    now: datetime.datetime,
    lines_added: int = 0,
    lines_removed: int = 0,
) -> ObservedEvent:
    sess = current_session(session, project) or open_session(session, project, now)
    ev = ObservedEvent(
        session_id=sess.id,
        project=project,
        path=path,
        kind=kind,
        lines_added=lines_added,
        lines_removed=lines_removed,
        actor=attr.actor,
        confidence=attr.confidence,
        basis=attr.basis,
        ts=now,
    )
    session.add(ev)
    sess.event_count = (sess.event_count or 0) + 1
    session.commit()
    return ev


def close_session(
    session: Session,
    sess: ObserverSession,
    now: datetime.datetime,
    closed_by: str,
) -> ObserverSession:
    sess.ended_at = now
    sess.closed_by = closed_by
    # pending_note, not written: closing and note-writing are separate steps so
    # a model outage cannot lose the session record.
    sess.note_state = PENDING
    session.commit()
    return sess


def _last_activity(session: Session, sess: ObserverSession) -> datetime.datetime:
    last = (
        session.query(func.max(ObservedEvent.ts))
        .filter(ObservedEvent.session_id == sess.id)
        .scalar()
    )
    return last or sess.started_at


def close_idle_sessions(
    session: Session, cfg: ObserverConfig, now: datetime.datetime
) -> list[ObserverSession]:
    """Close every open session idle longer than the configured window.

    Called both by the watch loop's tick and by the 30-minute background loop,
    so sessions still close correctly when the watcher is not running.
    """
    cutoff = datetime.timedelta(minutes=cfg.idle_minutes)
    closed: list[ObserverSession] = []
    for sess in (
        session.query(ObserverSession).filter(ObserverSession.ended_at.is_(None)).all()
    ):
        last = _last_activity(session, sess)
        # SQLite hands back naive datetimes even for timezone=True columns,
        # so a comparison against an aware `now` would raise rather than work.
        if last.tzinfo is None:
            last = last.replace(tzinfo=datetime.timezone.utc)
        if now - last >= cutoff:
            closed.append(close_session(session, sess, now, "idle"))
    return closed
