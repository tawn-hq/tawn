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

#: The analysis must announce itself with this heading. A model that returns
#: anything else — prose, a refusal, or an echo of the listing it was given — has
#: not produced an analysis, and accepting it would place unvalidated model text
#: in a document that reads as a record. Checked case-insensitively because
#: heading case is not worth a retry.
ANALYSIS_HEADING = "### what changed"

#: Cap on rendered event lines, so one enormous session cannot produce an
#: unreadable note.
MAX_LISTED_EVENTS = 200


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
    """Where a note belongs. Never None — a note always has somewhere to go.

    Notes live under `~/.tawn/reviews/<project>/<date>.md` by default.

    They used to be written to the first `write:` grant, on the reasoning that
    the Observer has no private write path. That reasoning was wrong on both
    counts. Tawn already writes `audit.jsonl`, `config.yaml`, `history/` and the
    ledger into its own home with no grant — the grant model governs access to
    *your* paths, not Tawn's. And using `write[0]` meant every project's notes
    landed in whichever directory happened to be granted first, so notes about
    `engine` were written into the `tawn` repository. A note with no write grant
    at all could never be written, leaving the session pending forever.

    Set `observer.notes_dir` in `~/.tawn/config.yaml` to put them somewhere else —
    a vault or a repo — in which case that path must be write-granted, because it
    is then one of *your* directories rather than Tawn's own.
    """
    from tawn.observer.config import load_observer_config

    configured = load_observer_config(Path(home)).notes_dir
    if not configured:
        return Path(home) / "reviews" / project / f"{day.isoformat()}.md"

    target = Path(configured).expanduser()
    grants = Grants.load(Path(home) / "grants.yaml")
    allowed = any(
        target == Path(w) or target.is_relative_to(Path(w)) for w in (grants.write or [])
    )
    if not allowed:
        # Configured somewhere Tawn may not write. Fall back to its own home
        # rather than dropping the note: losing the record is the worse outcome.
        return Path(home) / "reviews" / project / f"{day.isoformat()}.md"
    return target / project / f"{day.isoformat()}.md"


def review_target(home: Path, use_cloud: bool, model: str | None = None) -> str | None:
    """Which model writes the note: explicit > cloud chain > best local.

    Returned as a `default_router` target, so `None` means "use the configured
    preference and normal failover chain".

    `use_cloud` deliberately returns `None` rather than naming a provider: the
    router already orders cloud providers by which keys exist, and hardcoding one
    here would break the moment a key is removed.
    """
    if model:
        return model
    if use_cloud:
        return None
    from tawn.observer.config import load_observer_config, pick_local_review_model

    cfg = load_observer_config(Path(home))
    if cfg.review_model:
        return cfg.review_model
    try:
        from tawn.model.providers.ollama import OllamaProvider

        installed = [m["name"] for m in OllamaProvider().installed_models()]
    except Exception:
        return None
    picked = pick_local_review_model(installed)
    return f"ollama/{picked}" if picked else None


def _analyse(
    sess: ObserverSession,
    events: list[ObservedEvent],
    home: Path,
    use_cloud: bool,
    model: str | None = None,
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
        "This list is already printed in the document. Do not reproduce it.\n"
        "Write two short markdown sections and nothing else:\n"
        "### What changed\n"
        "Two or three sentences of substance, not a file list.\n"
        "### Worth another look\n"
        "Bullets naming specific files and why. If nothing warrants attention, "
        "say so in one line."
    )
    client = default_router(Path(home), target=review_target(home, use_cloud, model))
    resp = client.complete(
        [Message(role="user", content=prompt)], sensitive=not use_cloud
    )
    return resp.text


def _header(
    sess: ObserverSession,
    events: list[ObservedEvent],
    session: Session | None = None,
) -> str:
    added = sum(e.lines_added for e in events)
    removed = sum(e.lines_removed for e in events)
    start = sess.started_at.strftime("%H:%M")
    end = (sess.ended_at or sess.started_at).strftime("%H:%M")
    head = (
        f"## {start} – {end} · {sess.project}\n\n"
        f"**{len(events)} files · +{added} −{removed} · "
        f"closed by {sess.closed_by or 'idle'}**\n"
        f"Attribution: {attribution_summary(events)}\n"
    )
    if session is not None:
        # State the coverage claim explicitly. Without it a list of four files
        # reads as "these four changed" when the truth is "these four were
        # observed", and the reader has no way to tell the difference.
        from tawn.observer.sweep import coverage_line

        head += f"{coverage_line(session, sess.project)}\n"
    return head


def _changes(events: list[ObservedEvent]) -> str:
    """The changed-file list, rendered from the record.

    Deliberately not delegated to the model, even though the model is handed the
    same listing to reason over. A small model asked for prose will sometimes echo
    that listing back instead, and it corrupts paths doing so — observed live,
    `_observer-check.tmp.md` came back as `_observor-check.tmp.md`. A single wrong
    character inside a document that reads like a record is worse than no
    document, so facts never pass through a model on their way to the page.

    Low-confidence attribution is marked per line, matching `attribution_summary`:
    the hedge belongs everywhere the guess appears, not only in the total.
    """
    if not events:
        return "\n*No events recorded.*\n"
    shown = events[:MAX_LISTED_EVENTS]
    lines = [
        f"- {e.kind} {e.path} (+{e.lines_added} −{e.lines_removed}) "
        f"[{'' if e.confidence == 'high' else 'likely '}{e.actor}]"
        for e in shown
    ]
    if len(events) > len(shown):
        lines.append(f"- … {len(events) - len(shown)} more not listed")
    return "\n" + "\n".join(lines) + "\n"


def _valid_analysis(text: str) -> bool:
    """Whether the model returned something recognisable as the analysis."""
    return ANALYSIS_HEADING in (text or "").lower()


def compose(
    session: Session,
    sess: ObserverSession,
    home: Path,
    use_cloud: bool = False,
    model: str | None = None,
) -> tuple[str, str]:
    """Return (markdown, state). State is `written` or `unanalysed`.

    The facts — header and file list — are always rendered. The analysis is
    appended only when the model returns something that validates as one; an
    unrecognisable answer is treated exactly like no answer, because a note is a
    record first and a summary second.
    """
    events = _events(session, sess)
    body = _header(sess, events, session) + _changes(events)
    try:
        analysis = _analyse(sess, events, home, use_cloud, model).strip()
        if not _valid_analysis(analysis):
            # Not an exception from the model's point of view — it answered. It
            # just did not answer the question, and a plausible-looking
            # non-answer is the dangerous case, so it is discarded rather than
            # appended.
            raise ValueError("analysis missing the expected heading")
        body += "\n" + analysis + "\n"
        state = WRITTEN
    except Exception:
        # Losing the analysis must not lose the record.
        body += "\n*No usable analysis — facts recorded, analysis skipped.*\n"
        state = UNANALYSED
    return body, state


def _fail_attempt(session: Session, sess: ObserverSession) -> ObserverSession:
    sess.note_attempts += 1
    sess.note_state = FAILED if sess.note_attempts >= MAX_NOTE_ATTEMPTS else PENDING
    session.commit()
    return sess


def write_note(
    session: Session,
    sess: ObserverSession,
    home: Path,
    use_cloud: bool = False,
    model: str | None = None,
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

    body, state = compose(session, sess, home, use_cloud, model)
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


def reconcile_first(session: Session, home: Path, project: str | None = None) -> None:
    """Reconcile before composing, so the note's file list is actually complete.

    `write_note()` composes from whatever is in the database. Sweeping first is
    the difference between "these files were observed" and "these files changed",
    and it is the only point where that distinction is cheap to fix.

    Non-fatal: a sweep that cannot run must not block the note it was meant to
    improve.
    """
    try:
        from tawn.observer.sweep import sweep

        sweep(session, Path(home), project)
    except Exception:
        import logging

        logging.getLogger(__name__).warning("pre-review sweep failed", exc_info=True)


def process_pending(
    session: Session, home: Path, use_cloud: bool = False, model: str | None = None
) -> int:
    """Write notes for every session still waiting for one. Resumable."""
    pending = (
        session.query(ObserverSession)
        .filter(ObserverSession.note_state == PENDING)
        .all()
    )
    done = 0
    for sess in pending:
        write_note(session, sess, home, use_cloud, model)
        if sess.note_state in (WRITTEN, UNANALYSED):
            done += 1
    return done
