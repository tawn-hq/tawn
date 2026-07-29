"""Turning a closed session into a review note.

Improvement-oriented, not a changelog: what changed, what looks risky, what to
revisit. Notes append per project per day, so a day of work reads as one
document rather than a scatter of files.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from tawn.capability.grants import Grants
from tawn.memory.schema import ObservedEvent, ObserverSession

#: Bounds the retry loop rather than expressing a preference, so it is a
#: constant and not a config knob.
MAX_NOTE_ATTEMPTS = 3

WRITTEN = "written"
UNANALYSED = "unanalysed"
PENDING = "pending_note"
FAILED = "failed"


def _events(session: Session, sess: ObserverSession) -> list[ObservedEvent]:
    return (
        session.query(ObservedEvent)
        .filter(ObservedEvent.session_id == sess.id)
        .order_by(ObservedEvent.ts)
        .all()
    )


def attribution_summary(events: list[ObservedEvent]) -> str:
    """A one-line breakdown that hedges exactly where the evidence is weak.

    High-confidence counts are stated; low-confidence ones are prefixed
    "likely". A heuristic guess rendered as fact is the failure mode this whole
    tiering exists to avoid, so the hedge is not cosmetic.
    """
    high: dict[str, int] = {}
    low: dict[str, int] = {}
    for e in events:
        bucket = high if e.confidence == "high" else low
        bucket[e.actor] = bucket.get(e.actor, 0) + 1
    parts = [f"{n} {actor}" for actor, n in sorted(high.items(), key=lambda kv: -kv[1])]
    parts += [
        f"{n} likely {actor}" for actor, n in sorted(low.items(), key=lambda kv: -kv[1])
    ]
    return ", ".join(parts) or "no attribution"


def note_path_for(home: Path, project: str, day: datetime.date) -> Path | None:
    """Where a note belongs, or None when no `write:` grant exists.

    The Observer has no private write path — notes land only where the user
    already granted write access.
    """
    grants = Grants.load(Path(home) / "grants.yaml")
    if not grants.write:
        return None
    return Path(grants.write[0]) / "reviews" / project / f"{day.isoformat()}.md"


def _analyse(
    sess: ObserverSession, events: list[ObservedEvent], home: Path, use_cloud: bool
) -> str:
    """Ask the configured model for the analysis sections. Raises if none."""
    from tawn.model.router import default_router
    from tawn.model.types import Message

    listing = "\n".join(
        f"- {e.kind} {e.path} (+{e.lines_added} -{e.lines_removed}) [{e.actor}]"
        for e in events[:200]
    )
    prompt = (
        "You are reviewing one work session on a software project. Below are "
        "the files that changed, with line counts and who made each change.\n\n"
        f"{listing}\n\n"
        "Write two short markdown sections and nothing else:\n"
        "### What changed\n"
        "Two or three sentences of substance, not a file list.\n"
        "### Worth another look\n"
        "Bullets naming specific files and why. If nothing warrants attention, "
        "say so in one line."
    )
    client = default_router(Path(home))
    resp = client.complete(
        [Message(role="user", content=prompt)], sensitive=not use_cloud
    )
    return resp.text


def _header(sess: ObserverSession, events: list[ObservedEvent]) -> str:
    added = sum(e.lines_added for e in events)
    removed = sum(e.lines_removed for e in events)
    start = sess.started_at.strftime("%H:%M")
    end = (sess.ended_at or sess.started_at).strftime("%H:%M")
    return (
        f"## {start} – {end} · {sess.project}\n\n"
        f"**{len(events)} files · +{added} −{removed} · "
        f"closed by {sess.closed_by or 'idle'}**\n"
        f"Attribution: {attribution_summary(events)}\n"
    )


def compose(
    session: Session, sess: ObserverSession, home: Path, use_cloud: bool = False
) -> tuple[str, str]:
    """Return (markdown, state). State is `written` or `unanalysed`."""
    events = _events(session, sess)
    body = _header(sess, events)
    try:
        body += "\n" + _analyse(sess, events, home, use_cloud).strip() + "\n"
        state = WRITTEN
    except Exception:
        # Losing the analysis must not lose the record.
        body += "\n*No model available — facts recorded, analysis skipped.*\n"
        state = UNANALYSED
    return body, state


def _fail_attempt(session: Session, sess: ObserverSession) -> ObserverSession:
    sess.note_attempts += 1
    sess.note_state = FAILED if sess.note_attempts >= MAX_NOTE_ATTEMPTS else PENDING
    session.commit()
    return sess


def write_note(
    session: Session, sess: ObserverSession, home: Path, use_cloud: bool = False
) -> ObserverSession:
    from tawn.capability.audit import AuditLog, audit_path

    if sess.note_attempts >= MAX_NOTE_ATTEMPTS:
        sess.note_state = FAILED
        session.commit()
        return sess

    day = (sess.ended_at or sess.started_at).date()
    path = note_path_for(Path(home), sess.project, day)
    if path is None:
        return _fail_attempt(session, sess)

    body, state = compose(session, sess, home, use_cloud)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.stat().st_size if path.exists() else 0
        with path.open("a", encoding="utf-8") as fh:
            fh.write(("\n---\n\n" if existing else "") + body)
    except OSError:
        return _fail_attempt(session, sess)

    sess.note_path = str(path)
    sess.note_state = state
    sess.note_attempts += 1
    session.commit()
    try:
        AuditLog(audit_path(Path(home))).record(
            op="observe.note", target=str(path), ok=True, actor="system"
        )
    except Exception:
        pass
    return sess


def process_pending(session: Session, home: Path, use_cloud: bool = False) -> int:
    """Write notes for every session still waiting for one. Resumable."""
    pending = (
        session.query(ObserverSession)
        .filter(ObserverSession.note_state == PENDING)
        .all()
    )
    done = 0
    for sess in pending:
        write_note(session, sess, home, use_cloud)
        if sess.note_state in (WRITTEN, UNANALYSED):
            done += 1
    return done
