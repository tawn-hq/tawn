"""Append-only JSONL audit log (spec §10: "audit everything")."""

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, op: str, target: str, ok: bool, detail: str = "") -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "op": op,
            "target": target,
            "ok": ok,
            "detail": detail,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line]
