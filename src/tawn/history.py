"""Local-only chat history — append-only per-session JSONL at ~/.tawn/history/.

Each session is one file, chmod 600 (owner-read only). Never sent anywhere.
"""

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


#: A history line is one chat turn. Anything past this is not a turn — it is a
#: binary blob that reached the log through some other defect — and attempting to
#: parse a multi-megabyte line just to fail costs real time on a page load.
MAX_LINE_BYTES = 1_000_000


def _history_dir(home: Path) -> Path:
    d = home / "history"
    d.mkdir(parents=True, exist_ok=True)
    d.chmod(0o700)
    return d


def read_entries(path: Path) -> tuple[list[dict], int]:
    """Parse a session file, returning `(entries, skipped)`.

    One unreadable line must not cost the whole file, and one unreadable file
    must not cost the whole history index — a corrupt log is a reason to show
    less, never a reason to show nothing. Observed in practice: an attachment bug
    wrote hundreds of kilobytes of binary into a session file, and every history
    request then failed with a `JSONDecodeError`.

    `skipped` is returned rather than swallowed so callers can say what was lost.
    Quietly dropping lines would hide data loss, which is the failure this
    project cares most about avoiding.
    """
    if not path.exists():
        return [], 0
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], 0
    entries: list[dict] = []
    skipped = 0
    # `split("\n")` rather than `splitlines()`: the latter also breaks on \x0b,
    # \x1c-\x1e, \x85 and U+2028/9, so a single binary blob fragments into several
    # bogus "records" and inflates the skipped count. JSONL is newline-delimited,
    # and a valid line cannot contain a raw control character — JSON escapes them.
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) > MAX_LINE_BYTES:
            skipped += 1
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            skipped += 1
            continue
        if isinstance(obj, dict):
            entries.append(obj)
        else:
            skipped += 1
    return entries, skipped


class Session:
    def __init__(self, home: Path, session_id: str | None = None):
        self._dir = _history_dir(home)
        if session_id is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            session_id = f"{ts}-{uuid4().hex[:8]}"
        self.session_id = session_id
        self._path = self._dir / f"{session_id}.jsonl"
        # create with restricted permissions
        if not self._path.exists():
            self._path.touch(mode=0o600)
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)

    def append(self, role: str, content: str, model: str = "", tokens_in: int = 0, tokens_out: int = 0) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "content": content,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def entries(self) -> list[dict]:
        return read_entries(self._path)[0]


def list_sessions(home: Path) -> list[dict]:
    """Return metadata for all sessions, newest first.

    A session whose every line is unreadable is still listed, flagged rather than
    hidden: silently omitting it would make lost history look like history that
    never existed.
    """
    d = _history_dir(home)
    sessions = []
    for p in sorted(d.glob("*.jsonl"), reverse=True):
        entries, skipped = read_entries(p)
        if not entries and not skipped:
            continue
        user_entries = [e for e in entries if e.get("role") == "user"]
        if user_entries:
            title = str(user_entries[0].get("content", ""))[:60].strip() or p.stem
        else:
            title = p.stem
        first = entries[0] if entries else {}
        last = entries[-1] if entries else {}
        sessions.append({
            "id": p.stem,
            "title": title if entries else f"{p.stem} — unreadable",
            "started": first.get("ts", ""),
            "last": last.get("ts", ""),
            "turns": len(user_entries),
            "model": last.get("model", ""),
            "corrupt_lines": skipped,
        })
    return sessions


def get_session(home: Path, session_id: str) -> list[dict]:
    return read_entries(_history_dir(home) / f"{session_id}.jsonl")[0]
