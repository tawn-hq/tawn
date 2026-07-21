from typer.testing import CliRunner

import tawn
from tawn.cli import app

runner = CliRunner()


def test_bare_tawn_shows_branded_status(tawn_home, tmp_path, monkeypatch):
    monkeypatch.setenv("TAWN_DB_URL", f"sqlite+pysqlite:///{tmp_path}/t.db")
    result = runner.invoke(app, [])
    assert result.exit_code == 0, result.output
    out = result.output.lower()
    assert "tawn" in out
    assert "the twin you own" in out
    assert tawn.__version__ in result.output
    # bare tawn when uninitialized shows init prompt
    assert "not initialized" in out or "tawn init" in out


def test_bare_tawn_hints_init_when_uninitialized(tawn_home, tmp_path, monkeypatch):
    monkeypatch.setenv("TAWN_DB_URL", f"sqlite+pysqlite:///{tmp_path}/t.db")
    result = runner.invoke(app, [])
    assert "tawn init" in result.output


def test_subcommands_still_work(tawn_home):
    assert runner.invoke(app, ["init"]).exit_code == 0
