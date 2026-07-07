from typer.testing import CliRunner

from tawn.cli import app

runner = CliRunner()


def test_init_creates_home_and_deny_all_grants(tawn_home):
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert (tawn_home / "raw" / "agent-notes").is_dir()
    assert "read: []" in (tawn_home / "grants.yaml").read_text()
    assert (tawn_home / "grants.yaml.sha256").exists()
    assert (tawn_home / "audit.log").exists()


def test_init_is_safe_to_rerun_and_preserves_edits(tawn_home):
    runner.invoke(app, ["init"])
    grants = tawn_home / "grants.yaml"
    grants.write_text("read: ['~/code']\n")
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert grants.read_text() == "read: ['~/code']\n"  # never clobbered


def test_grant_list_shows_deny_all(tawn_home):
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["grant", "list"])
    assert result.exit_code == 0
    assert "read: (none)" in result.output
    assert "write: (none)" in result.output
    assert "system: off" in result.output


def test_grant_list_fails_on_tampered_file(tawn_home):
    runner.invoke(app, ["init"])
    (tawn_home / "grants.yaml").write_text("read: ['~/everything']\n")
    result = runner.invoke(app, ["grant", "list"])
    assert result.exit_code == 1
    assert "grant confirm" in result.output


def test_grant_confirm_accepts_edit(tawn_home):
    runner.invoke(app, ["init"])
    (tawn_home / "grants.yaml").write_text("read: ['~/code']\nwrite: []\n")
    assert runner.invoke(app, ["grant", "confirm"]).exit_code == 0
    result = runner.invoke(app, ["grant", "list"])
    assert result.exit_code == 0 and "code" in result.output
