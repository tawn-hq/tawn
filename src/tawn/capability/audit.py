"""Append-only JSONL audit log (spec §10: "audit everything").

Immutability contract: every entry includes a sha256 chain hash linking it
to the previous entry — tampering breaks the chain. File is chmod 600.
"""

import csv
import hashlib
import io
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "genesis"
        lines = [l for l in self.path.read_text().splitlines() if l]
        if not lines:
            return "genesis"
        return json.loads(lines[-1]).get("chain", "genesis")

    def record(self, op: str, target: str, ok: bool, detail: str = "", actor: str = "system") -> None:
        """actor: who initiated this — "cli" | "web" | "chat" | "mcp" | "system"
        (background jobs: auto-compiler, scheduled snapshots, federation watcher).
        """
        prev_hash = self._last_hash()
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "op": op,
            "target": target,
            "ok": ok,
            "detail": detail,
            "actor": actor,
        }
        # chain hash = sha256 of prev_hash + this entry (without chain field)
        payload = prev_hash + json.dumps(entry, sort_keys=True)
        entry["chain"] = hashlib.sha256(payload.encode()).hexdigest()[:16]
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        # restrict file to owner-only after every write
        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def entries(self, limit: int = 0, offset: int = 0) -> list[dict]:
        if not self.path.exists():
            return []
        all_entries = [json.loads(line) for line in self.path.read_text().splitlines() if line]
        if offset:
            all_entries = all_entries[offset:]
        if limit:
            all_entries = all_entries[:limit]
        return all_entries

    def verify_chain(self) -> bool:
        """Returns True if no tampering detected."""
        all_entries = self.entries()
        prev = "genesis"
        for entry in all_entries:
            chain = entry.pop("chain", "")
            payload = prev + json.dumps(entry, sort_keys=True)
            expected = hashlib.sha256(payload.encode()).hexdigest()[:16]
            entry["chain"] = chain
            if chain != expected:
                return False
            prev = chain
        return True

    def export_csv(self) -> str:
        buf = io.StringIO()
        fields = ["ts", "op", "target", "ok", "detail", "actor", "chain"]
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(self.entries())
        return buf.getvalue()

    def export_json(self) -> str:
        return json.dumps(self.entries(), indent=2)
