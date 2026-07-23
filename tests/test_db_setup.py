import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from tawn.cli import app
from tawn.dbsetup import ensure_database, probe

runner = CliRunner()


def _pg_available() -> bool:
    exe = shutil.which("pg_isready")
    return bool(exe) and subprocess.run([exe], capture_output=True).returncode == 0


def test_probe_sqlite_always_fine(tmp_path):
    st = probe(f"sqlite+pysqlite:///{tmp_path}/t.db")
    assert st.server_up and st.can_connect


def test_db_setup_cli_is_idempotent(tawn_home, tmp_path, monkeypatch):
    monkeypatch.setenv("TAWN_DB_URL", f"sqlite+pysqlite:///{tmp_path}/t.db")
    first = runner.invoke(app, ["db", "setup"])
    second = runner.invoke(app, ["db", "setup"])
    assert first.exit_code == 0, first.output
    assert second.exit_code == 0
    assert "ready" in second.output


@pytest.mark.skipif(not _pg_available(), reason="no local postgres")
def test_ensure_database_against_real_postgres():
    st = ensure_database("postgresql+psycopg:///tawn_test_stage1")
    assert st.server_up and st.db_exists and st.can_connect
    # cleanup
    import sqlalchemy as sa

    admin = sa.create_engine(
        "postgresql+psycopg:///postgres", isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as c:
        c.execute(sa.text("DROP DATABASE IF EXISTS tawn_test_stage1"))


def test_doctor_reports_rows(tawn_home, tmp_path, monkeypatch):
    monkeypatch.setenv("TAWN_DB_URL", f"sqlite+pysqlite:///{tmp_path}/t.db")
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    for check in ("python", "home", "grants", "database"):
        assert check in result.output.lower()
