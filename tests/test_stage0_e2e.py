"""Spec §12.2: attempts to read/write outside grants must fail at the
FS-mediation layer — on a completely fresh install."""

import pytest
from typer.testing import CliRunner

from tawn.capability.audit import AuditLog
from tawn.capability.fs import GrantError, MediatedFS
from tawn.capability.grants import load_verified
from tawn.cli import app

def test_fresh_install_denies_the_world(tawn_home, tmp_path):
    assert CliRunner().invoke(app, ["init"]).exit_code == 0

    grants = load_verified(tawn_home / "grants.yaml")
    fs = MediatedFS(grants, AuditLog(tawn_home / "audit.log"), home=tawn_home)

    outside = tmp_path / "user-file.txt"
    outside.write_text("private")

    with pytest.raises(GrantError):
        fs.read_text(outside)
    with pytest.raises(GrantError):
        fs.write_text(tmp_path / "new.txt", "x")

    # …but Tawn's own write-back path works (raw/ under home):
    fs.write_text(tawn_home / "raw" / "agent-notes" / "note.md", "durable learning")

    # and both denials are on the audit record:
    denied = [e for e in fs.audit.entries() if not e["ok"]]
    assert len(denied) == 2
