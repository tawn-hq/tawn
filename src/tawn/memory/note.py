"""note() verb — append a structured note to raw/agent-notes/."""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml

from tawn.compiler.compiler import request_compile
from tawn.home import tawn_home


def note(
    payload: str,
    domain: str | None = None,
    type: str = "observation",
    confidence: str = "medium",
    source: str | None = None,
    ttl_days: int | None = None,
    home: Path | None = None,
) -> dict:
    """Append a note to raw/agent-notes/YYYY-MM-DD.md and queue a compile.

    Returns {"ok": True, "path": str, "compile_queued": True}.
    Raises ValueError for empty payload.
    """
    if not payload or not payload.strip():
        raise ValueError("note payload cannot be empty")

    home = home or tawn_home()
    today = datetime.date.today().strftime("%Y-%m-%d")
    notes_dir = home / "raw" / "agent-notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    path = notes_dir / f"{today}.md"

    from tawn.memory.notes import new_note_id

    fm: dict = {
        "type": type,
        "asof": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        # A stable handle so the note can be edited or deleted later. Day
        # files are append-only, so position alone is not an identity.
        "note_id": new_note_id(),
    }
    if domain:
        fm["domain"] = domain
    if confidence != "medium":
        fm["confidence"] = confidence
    if source:
        fm["source"] = source
    if ttl_days is not None:
        fm["ttl_days"] = ttl_days

    fm_text = yaml.dump(fm, default_flow_style=False).strip()
    entry = f"\n---\n{fm_text}\n---\n{payload.strip()}\n"

    with path.open("a", encoding="utf-8") as f:
        f.write(entry)

    request_compile(home)

    return {
        "ok": True,
        "path": str(path),
        "compile_queued": True,
    }
