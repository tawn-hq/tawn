import json
from pathlib import Path

from tawn.capability.audit import AuditLog, audit_path, migrate_audit_log


def _write(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def _entry(ts: str, op: str, actor: str = "cli") -> dict:
    return {"ts": ts, "op": op, "target": "t", "ok": True, "detail": "", "actor": actor}


def test_audit_path_is_jsonl(tmp_path):
    assert audit_path(tmp_path).name == "audit.jsonl"


def test_migration_noop_without_legacy_file(tmp_path):
    assert migrate_audit_log(tmp_path) is False


def test_migration_merges_by_timestamp(tmp_path):
    _write(tmp_path / "audit.log", [
        _entry("2026-07-02T00:00:00+00:00", "b"),
        _entry("2026-07-04T00:00:00+00:00", "d"),
    ])
    _write(tmp_path / "audit.jsonl", [
        _entry("2026-07-01T00:00:00+00:00", "a", "web"),
        _entry("2026-07-03T00:00:00+00:00", "c", "web"),
    ])

    assert migrate_audit_log(tmp_path) is True

    log = AuditLog(audit_path(tmp_path))
    assert [e["op"] for e in log.entries()] == ["a", "b", "c", "d"]
    assert log.verify_chain()["intact"] is True


def test_migration_backup_is_timestamped_and_legacy_removed(tmp_path):
    _write(tmp_path / "audit.log", [_entry("2026-07-02T00:00:00+00:00", "b")])

    migrate_audit_log(tmp_path)

    assert not (tmp_path / "audit.log").exists()
    assert len(list(tmp_path.glob("audit.log.premerge-*"))) == 1


def test_migration_is_idempotent(tmp_path):
    _write(tmp_path / "audit.log", [_entry("2026-07-02T00:00:00+00:00", "b")])

    assert migrate_audit_log(tmp_path) is True
    assert migrate_audit_log(tmp_path) is False
    assert len(AuditLog(audit_path(tmp_path)).entries()) == 1


def test_second_migration_does_not_clobber_first_backup(tmp_path):
    """A reappearing audit.log must not overwrite an earlier backup."""
    _write(tmp_path / "audit.log", [_entry("2026-07-02T00:00:00+00:00", "first")])
    migrate_audit_log(tmp_path)
    _write(tmp_path / "audit.log", [_entry("2026-07-05T00:00:00+00:00", "second")])
    migrate_audit_log(tmp_path)

    assert len(list(tmp_path.glob("audit.log.premerge-*"))) == 2


def test_migration_skips_when_lock_held(tmp_path):
    """Concurrent starts must not both rewrite the file.

    The CLI, web daemon and MCP server all start independently, and a stale
    daemon racing the CLI is exactly what corrupted Stage 7.
    """
    import fcntl

    _write(tmp_path / "audit.log", [_entry("2026-07-02T00:00:00+00:00", "b")])
    lock = tmp_path / "audit.migrate.lock"
    lock.touch()
    with lock.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert migrate_audit_log(tmp_path) is False
        fcntl.flock(fh, fcntl.LOCK_UN)

    assert (tmp_path / "audit.log").exists()  # untouched while locked


def test_verify_chain_reports_break_location(tmp_path):
    log = AuditLog(audit_path(tmp_path))
    log.record("a", "/x", ok=True, actor="cli")
    log.record("b", "/y", ok=True, actor="cli")
    log.record("c", "/z", ok=True, actor="cli")

    lines = audit_path(tmp_path).read_text().splitlines()
    tampered = json.loads(lines[1])
    tampered["target"] = "/tampered"
    lines[1] = json.dumps(tampered)
    audit_path(tmp_path).write_text("\n".join(lines) + "\n")

    result = log.verify_chain()
    assert result["intact"] is False
    assert result["first_break_index"] == 1
    assert result["entries"] == 3


def test_verify_chain_on_empty_log(tmp_path):
    result = AuditLog(audit_path(tmp_path)).verify_chain()
    assert result["intact"] is True
    assert result["entries"] == 0
    assert result["first_break_index"] is None


def test_no_source_file_hardcodes_the_legacy_path():
    """The bug was a second hardcoded path, so guard against a third.

    Writers appended to `audit.log` while the API read `audit.jsonl`; the
    Dashboard panel, Settings view, chain-verify button and CSV export all
    reported on a file nothing wrote to. Only audit.py may name the legacy
    file, and only in order to migrate it away.
    """
    import subprocess

    root = Path(__file__).resolve().parents[1] / "src" / "tawn"
    hits = subprocess.run(
        ["grep", "-rn", '"audit.log"', str(root), "--include=*.py"],
        capture_output=True, text=True,
    ).stdout.strip().splitlines()
    offenders = [h for h in hits if "/capability/audit.py:" not in h]
    assert not offenders, f"hardcoded legacy audit path: {offenders}"
