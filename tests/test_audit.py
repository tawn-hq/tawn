from tawn.capability.audit import AuditLog


def test_record_appends_json_lines(tmp_path):
    log = AuditLog(tmp_path / "audit.log")
    log.record("fs.read", "/some/path", ok=True)
    log.record("fs.write", "/other/path", ok=False, detail="no write grant")
    entries = log.entries()
    assert len(entries) == 2
    assert entries[0]["op"] == "fs.read" and entries[0]["ok"] is True
    assert entries[1]["detail"] == "no write grant"
    assert "ts" in entries[0]


def test_log_file_is_append_only_across_instances(tmp_path):
    path = tmp_path / "audit.log"
    AuditLog(path).record("a", "x", ok=True)
    AuditLog(path).record("b", "y", ok=True)
    assert [e["op"] for e in AuditLog(path).entries()] == ["a", "b"]
