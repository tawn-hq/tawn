from typer.testing import CliRunner

from tawn.cli import app

runner = CliRunner()


def test_init_creates_home_and_deny_all_grants(tawn_home):
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert (tawn_home / "raw" / "agent-notes").is_dir()
    assert "read: []" in (tawn_home / "grants.yaml").read_text()
    assert (tawn_home / "grants.yaml.sha256").exists()
    assert (tawn_home / "audit.jsonl").exists()


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


# ── web stop / status control flow ────────────────────────────────────────────

def test_web_stop_when_not_running(tawn_home):
    """Regression: an edit once left `port` referenced outside its branch,
    so `tawn web stop` died with UnboundLocalError and the daemon never
    stopped. Nothing covered these paths."""
    from typer.testing import CliRunner
    from tawn.cli import app

    result = CliRunner().invoke(app, ["web", "stop"])
    assert result.exit_code == 0
    assert "not running" in result.stdout.lower()


def test_web_status_when_not_running(tawn_home):
    from typer.testing import CliRunner
    from tawn.cli import app

    result = CliRunner().invoke(app, ["web", "status"])
    assert result.exit_code == 0
    assert "stopped" in result.stdout.lower()


def test_web_status_warns_when_code_is_stale(tawn_home, monkeypatch):
    """A daemon older than the code on disk must say so where the user looks."""
    from typer.testing import CliRunner
    import tawn.cli as cli_mod
    from tawn.cli import app

    monkeypatch.setattr(cli_mod, "_web_is_running", lambda home: (True, 4242))
    monkeypatch.setattr(
        "tawn.staleness.staleness_report",
        lambda home, name, current=None: {
            "process": name, "running": "old", "current": "new",
            "stale": True, "advice": "restart it",
        },
    )
    result = CliRunner().invoke(app, ["web", "status"])
    assert "older than what is on disk" in result.stdout


def test_version_matches_package_metadata():
    """Regression: __version__ was a hardcoded string that drifted from
    pyproject.toml, so the update page reported 0.1.0 while 0.2.0 ran."""
    import importlib.metadata as md

    import tawn

    assert tawn.__version__ == md.version("tawn")


def test_version_is_read_from_package_metadata():
    """The value must be derived, not typed in — that is what drifted."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src" / "tawn" / "__init__.py").read_text()
    assert "importlib.metadata" in src
    assert '_pkg_version("tawn")' in src


def test_update_not_offered_when_local_build_is_ahead():
    """Being ahead of PyPI is not an available update.

    A plain `latest != current` told users to "update" to an older release
    whenever they ran a local build newer than the published one.
    """
    from tawn.updater import _is_newer

    assert _is_newer("0.2.0", "0.1.0") is True
    assert _is_newer("0.1.0", "0.2.0") is False
    assert _is_newer("0.2.0", "0.2.0") is False
    assert _is_newer(None, "0.2.0") is False
