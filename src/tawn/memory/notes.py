"""Read, edit and delete the personal notes stored in raw/agent-notes/.

`note()` appends YAML-fenced blocks to one markdown file per day, which is
right for writing but gives nothing to edit against: there is no handle for
"that note I wrote on Tuesday". This parses the day files back into
individually addressable notes.

Notes written from now on carry a `note_id` in their frontmatter. Older ones
have none, so their id is derived from the file and their position in it —
stable as long as earlier notes in the same file are not deleted, which is
the best that can be done without rewriting history.
"""

from __future__ import annotations

import datetime
import re
import uuid
from pathlib import Path

import yaml

_BLOCK = re.compile(r"^---\s*$", re.MULTILINE)


def notes_dir(home: Path) -> Path:
    return Path(home) / "raw" / "agent-notes"


def new_note_id() -> str:
    return uuid.uuid4().hex[:12]


def _parse_file(path: Path) -> list[dict]:
    """Split one day file into its note blocks."""
    text = path.read_text(encoding="utf-8", errors="replace")
    out: list[dict] = []

    # Blocks look like: ---\n<yaml>\n---\n<body>, repeated. Splitting on the
    # fence and walking in pairs is more forgiving of stray blank lines than
    # a single monolithic regex.
    parts = _BLOCK.split(text)
    idx = 0
    i = 0
    while i < len(parts) - 1:
        raw_fm = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        if not raw_fm:
            i += 1
            continue
        try:
            fm = yaml.safe_load(raw_fm) or {}
        except yaml.YAMLError:
            i += 2
            continue
        if not isinstance(fm, dict):
            i += 2
            continue

        out.append({
            "id": fm.get("note_id") or f"{path.stem}:{idx}",
            "note_id": fm.get("note_id"),
            "file": str(path),
            "index": idx,
            "type": fm.get("type", "observation"),
            "domain": fm.get("domain"),
            "confidence": fm.get("confidence", "medium"),
            "asof": fm.get("asof"),
            "ttl_days": fm.get("ttl_days"),
            "body": body.strip(),
        })
        idx += 1
        i += 2
    return out


def list_notes(home: Path, domain: str | None = None) -> list[dict]:
    """All notes, newest file first."""
    d = notes_dir(home)
    if not d.is_dir():
        return []
    notes: list[dict] = []
    for path in sorted(d.glob("*.md"), reverse=True):
        notes.extend(_parse_file(path))
    if domain:
        notes = [n for n in notes if n.get("domain") == domain]
    notes.sort(key=lambda n: n.get("asof") or "", reverse=True)
    return notes


def get_note(home: Path, note_id: str) -> dict | None:
    return next((n for n in list_notes(home) if n["id"] == note_id), None)


def _rewrite_file(path: Path, notes: list[dict]) -> None:
    """Write a day file back from its parsed notes."""
    chunks: list[str] = []
    for n in notes:
        fm: dict = {"type": n.get("type", "observation")}
        if n.get("asof"):
            fm["asof"] = n["asof"]
        if n.get("domain"):
            fm["domain"] = n["domain"]
        if n.get("confidence") and n["confidence"] != "medium":
            fm["confidence"] = n["confidence"]
        if n.get("ttl_days") is not None:
            fm["ttl_days"] = n["ttl_days"]
        fm["note_id"] = n.get("note_id") or new_note_id()

        fm_text = yaml.dump(fm, default_flow_style=False, sort_keys=True).strip()
        chunks.append(f"\n---\n{fm_text}\n---\n{n['body'].strip()}\n")
    path.write_text("".join(chunks), encoding="utf-8")


def update_note(home: Path, note_id: str, body: str | None = None, domain: str | None = None) -> dict | None:
    """Edit a note in place. Returns the updated note, or None if not found."""
    target = get_note(home, note_id)
    if target is None:
        return None

    path = Path(target["file"])
    notes = _parse_file(path)
    for n in notes:
        if n["id"] != note_id:
            continue
        if body is not None:
            n["body"] = body
        if domain is not None:
            n["domain"] = domain or None
        # Editing changes what the note says, so it is no longer the text
        # that was compiled — mark it for recompilation.
        n["asof"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        n["note_id"] = n.get("note_id") or note_id
    _rewrite_file(path, notes)

    from tawn.compiler.compiler import request_compile
    request_compile(Path(home))
    return get_note(home, note_id) or next((n for n in notes if n["id"] == note_id), None)


def delete_note(home: Path, note_id: str) -> bool:
    target = get_note(home, note_id)
    if target is None:
        return False
    path = Path(target["file"])
    remaining = [n for n in _parse_file(path) if n["id"] != note_id]
    _rewrite_file(path, remaining)

    from tawn.compiler.compiler import request_compile
    request_compile(Path(home))
    return True
