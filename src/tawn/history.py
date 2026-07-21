"""Local-only chat history — append-only per-session JSONL at ~/.tawn/history/.

Each session is one file, chmod 600 (owner-read only). Never sent anywhere.
"""

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _history_dir(home: Path) -> Path:
    d = home / "history"
    d.mkdir(parents=True, exist_ok=True)
    d.chmod(0o700)
    return d


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
        if not self._path.exists():
            return []
        return [json.loads(line) for line in self._path.read_text().splitlines() if line]


def list_sessions(home: Path) -> list[dict]:
    """Return metadata for all sessions, newest first."""
    d = _history_dir(home)
    sessions = []
    for p in sorted(d.glob("*.jsonl"), reverse=True):
        lines = [l for l in p.read_text().splitlines() if l]
        if not lines:
            continue
        first = json.loads(lines[0])
        last = json.loads(lines[-1])
        sessions.append({
            "id": p.stem,
            "started": first.get("ts", ""),
            "last": last.get("ts", ""),
            "turns": len([l for l in lines if json.loads(l).get("role") == "user"]),
            "model": last.get("model", ""),
        })
    return sessions


def get_session(home: Path, session_id: str) -> list[dict]:
    p = _history_dir(home) / f"{session_id}.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line]
