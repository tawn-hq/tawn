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

    def verify_chain(self) -> dict:
        """Walk the chain, reporting *where* it breaks rather than just whether.

        Returns {intact, entries, first_break_index, first_break_ts}.

        A bare boolean is what let a stale file look healthy: the API verified
        `audit.jsonl` while every writer appended to `audit.log`, so
        `intact: true` was reporting on 408 bytes of unrelated history. Naming
        the break location makes a failure actionable and a pass meaningful.
        """
        all_entries = self.entries()
        prev = "genesis"
        for i, entry in enumerate(all_entries):
            chain = entry.pop("chain", "")
            payload = prev + json.dumps(entry, sort_keys=True)
            expected = hashlib.sha256(payload.encode()).hexdigest()[:16]
            entry["chain"] = chain
            if chain != expected:
                return {
                    "intact": False,
                    "entries": len(all_entries),
                    "first_break_index": i,
                    "first_break_ts": entry.get("ts"),
                }
            prev = chain
        return {
            "intact": True,
            "entries": len(all_entries),
            "first_break_index": None,
            "first_break_ts": None,
        }

    def export_csv(self) -> str:
        buf = io.StringIO()
        fields = ["ts", "op", "target", "ok", "detail", "actor", "chain"]
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(self.entries())
        return buf.getvalue()

    def export_json(self) -> str:
        return json.dumps(self.entries(), indent=2)


# ── One audit file ────────────────────────────────────────────────────────────

def audit_path(home: Path) -> Path:
    """The one audit file.

    Content has always been JSONL; the historical `.log` name is what let a
    second file drift apart unnoticed. Every writer appended to `audit.log`
    while `/api/audit*` read `audit.jsonl`, so the Dashboard panel, Settings
    view, chain-verify button and CSV export all reported on a file nothing
    wrote to — for two days, with `intact: true`.
    """
    return Path(home) / "audit.jsonl"


def _read_entries(path: Path) -> list[dict]:
    """Parse a JSONL audit file, skipping unparseable lines.

    A partial trailing write is not a reason to lose everything before it.
    """
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _rechain(entries: list[dict]) -> list[dict]:
    """Recompute the hash chain across a sequence, seeded like `_last_hash`."""
    prev = "genesis"
    out: list[dict] = []
    for entry in entries:
        body = {k: v for k, v in entry.items() if k != "chain"}
        payload = prev + json.dumps(body, sort_keys=True)
        body["chain"] = hashlib.sha256(payload.encode()).hexdigest()[:16]
        prev = body["chain"]
        out.append(body)
    return out


def migrate_audit_log(home: Path) -> bool:
    """Merge a legacy `audit.log` into `audit.jsonl`. True if a merge ran.

    Locked, because the CLI, web daemon and MCP server all start
    independently and would otherwise merge and rewrite the same file
    concurrently — a stale daemon racing the CLI is exactly the shape of bug
    that corrupted Stage 7. Written to a temp file and atomically replaced,
    so a crash mid-write leaves the original intact rather than a
    half-written audit trail.

    Recomputing rewrites existing chain values. That is acceptable only
    because those values were never protecting the live log.
    """
    import fcntl
    import tempfile

    home = Path(home)
    legacy = home / "audit.log"
    if not legacy.exists():
        return False

    home.mkdir(parents=True, exist_ok=True)
    lock_path = home / "audit.migrate.lock"
    lock_path.touch(exist_ok=True)

    with lock_path.open("w") as lock_fh:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False  # another process is already doing this

        if not legacy.exists():  # won the race but lost the work
            return False

        target = audit_path(home)
        merged = _read_entries(target) + _read_entries(legacy)
        merged.sort(key=lambda e: e.get("ts", ""))
        merged = _rechain(merged)

        fd, tmp_name = tempfile.mkstemp(dir=str(home), prefix=".audit-merge-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for entry in merged:
                fh.write(json.dumps(entry) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
        target.chmod(stat.S_IRUSR | stat.S_IWUSR)

        # Microsecond resolution, plus a collision guard: two migrations in
        # the same second would otherwise share a name and the second would
        # silently overwrite the first backup.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        backup = home / f"audit.log.premerge-{stamp}"
        suffix = 1
        while backup.exists():
            backup = home / f"audit.log.premerge-{stamp}-{suffix}"
            suffix += 1
        legacy.rename(backup)
        return True
