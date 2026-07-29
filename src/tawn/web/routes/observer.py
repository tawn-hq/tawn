"""Ambient Observer — projects, sessions, and forced reviews."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from tawn.capability.grants import Grants
from tawn.db import get_session
from tawn.home import tawn_home
from tawn.memory.schema import ObservedEvent, ObserverSession
from tawn.observer.projects import discover_projects
from tawn.observer.review import attribution_summary, process_pending
from tawn.observer.sessions import close_session, current_session

router = APIRouter(tags=["observer"])


def _grants() -> Grants:
    return Grants.load(tawn_home() / "grants.yaml")


@router.get("/projects")
def get_projects():
    grants = _grants()
    return {
        "observe": grants.observe,
        "projects": [
            {"name": p.name, "root": str(p.root), "is_git": p.is_git}
            for p in discover_projects(grants)
        ],
    }


@router.get("/sessions")
def get_sessions(
    project: str | None = None,
    limit: int = 40,
    session: Session = Depends(get_session),
):
    q = session.query(ObserverSession)
    if project:
        q = q.filter(ObserverSession.project == project)
    rows = q.order_by(ObserverSession.started_at.desc()).limit(limit).all()
    out = []
    for s in rows:
        events = (
            session.query(ObservedEvent).filter(ObservedEvent.session_id == s.id).all()
        )
        out.append(
            {
                "id": s.id,
                "project": s.project,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "closed_by": s.closed_by,
                "event_count": s.event_count,
                "lines_added": sum(e.lines_added for e in events),
                "lines_removed": sum(e.lines_removed for e in events),
                "attribution": attribution_summary(events),
                "note_path": s.note_path,
                "note_state": s.note_state,
            }
        )
    return {"sessions": out}


@router.get("/sessions/{session_id}/events")
def get_events(session_id: int, session: Session = Depends(get_session)):
    rows = (
        session.query(ObservedEvent)
        .filter(ObservedEvent.session_id == session_id)
        .order_by(ObservedEvent.ts)
        .all()
    )
    return {
        "events": [
            {
                "path": e.path,
                "kind": e.kind,
                "actor": e.actor,
                "confidence": e.confidence,
                "basis": e.basis,
                "lines_added": e.lines_added,
                "lines_removed": e.lines_removed,
                "ts": e.ts.isoformat() if e.ts else None,
            }
            for e in rows
        ]
    }


@router.post("/review")
def post_review(
    project: str | None = None,
    cloud: bool = False,
    session: Session = Depends(get_session),
):
    now = datetime.datetime.now(datetime.timezone.utc)
    home = tawn_home()
    names = (
        [project]
        if project
        else [p.name for p in discover_projects(_grants())]
    )
    closed = 0
    for name in names:
        sess = current_session(session, name)
        if sess is not None:
            close_session(session, sess, now, "manual")
            closed += 1
    return {"closed": closed, "notes_written": process_pending(session, home, cloud)}
