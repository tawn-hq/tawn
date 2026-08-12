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
from tawn.observer.review import (
    attribution_summary,
    process_pending,
    reconcile_first,
)
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


@router.get("/review-models")
def get_review_models():
    """What can write a review note, and what would be picked right now.

    Reports only what exists: installed local chat models, and the live catalogue
    of every cloud provider whose key is actually set. Offering an option that
    cannot run is worse than offering fewer.

    `source` per row is "live", "cache" or "fallback", so the caller can say
    whether it is showing the real catalogue or a stale stand-in rather than
    presenting both alike.
    """
    from tawn.model.providers.ollama import OllamaProvider
    from tawn.model.router import usable_models
    from tawn.observer.config import is_chat_capable
    from tawn.observer.review import review_target

    home = tawn_home()
    try:
        local = [
            f"ollama/{m['name']}"
            for m in OllamaProvider().installed_models()
            if is_chat_capable(m["name"])
        ]
    except Exception:
        local = []

    # Specific models, not bare provider names. A provider name alone routes to
    # whatever that provider's default happens to be, which is useless for
    # OpenRouter — it fronts hundreds of models and the choice is the point.
    # `usable_models` already asks each keyed provider for its live catalogue and
    # caches for a day, so this costs nothing on the common path.
    cloud: list[dict] = []
    try:
        cloud = [
            {"target": r["target"], "provider": r["provider"],
             "model": r["model"], "source": r["source"]}
            for r in usable_models(home)
            if r["locality"] == "cloud"
        ]
    except Exception:
        cloud = []

    return {
        "local": local,
        "cloud": [c["target"] for c in cloud],
        "cloud_detail": cloud,
        "providers": sorted({c["provider"] for c in cloud}),
        "default": review_target(home, use_cloud=False),
        "cloud_available": bool(cloud),
    }


@router.post("/review")
def post_review(
    project: str | None = None,
    cloud: bool = False,
    model: str | None = None,
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
    reconcile_first(session, home, project)
    written = process_pending(session, home, cloud, model)
    return {
        "closed": closed,
        "notes_written": written,
        "model": model or ("cloud chain" if cloud else review_target_label(home)),
    }


@router.get("/sessions/{session_id}/note")
def get_note(session_id: int, session: Session = Depends(get_session)):
    """The written note, or why there isn't one.

    Read through the same path the writer used rather than served from a cached
    copy: a note the user has since edited or deleted should read as edited or
    deleted, not as whatever was true when it was generated.
    """
    from pathlib import Path as _Path

    sess = session.get(ObserverSession, session_id)
    if sess is None:
        return {"found": False, "reason": "no such session"}
    if not sess.note_path:
        return {
            "found": False,
            "state": sess.note_state,
            "reason": "no note written yet — run a review",
        }
    p = _Path(sess.note_path)
    if not p.exists():
        return {
            "found": False,
            "state": sess.note_state,
            "path": str(p),
            "reason": "the note file has been moved or deleted",
        }
    try:
        body = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"found": False, "path": str(p), "reason": f"unreadable: {exc}"}
    return {"found": True, "state": sess.note_state, "path": str(p), "body": body}


@router.post("/sweep")
def post_sweep(
    project: str | None = None,
    dry_run: bool = False,
    session: Session = Depends(get_session),
):
    """Reconcile the record against git and the filesystem snapshot."""
    from tawn.observer.sweep import sweep

    results = sweep(session, tawn_home(), project, dry_run=dry_run)
    return {
        "dry_run": dry_run,
        "results": [
            {
                "project": r.project,
                "commits_read": r.commits_read,
                "events_added": r.events_added,
                "events_updated": r.events_updated,
                "skipped_existing": r.skipped_existing,
                "reason": r.reason,
            }
            for r in results
        ],
    }


def review_target_label(home) -> str:
    from tawn.observer.review import review_target

    return review_target(home, use_cloud=False) or "default chain"
