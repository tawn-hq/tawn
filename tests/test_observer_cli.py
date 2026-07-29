from typer.testing import CliRunner

from tawn.cli import app

runner = CliRunner()


def test_status_says_why_it_is_off(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    (tawn_home / "grants.yaml").write_text("read: []\nwrite: []\nobserve: []\n")
    r = runner.invoke(app, ["observe", "status"])
    assert r.exit_code == 0
    assert "observe: is empty" in r.stdout


def test_projects_is_empty_without_read_grants(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    (tawn_home / "grants.yaml").write_text("read: []\nwrite: []\nobserve: [fs]\n")
    r = runner.invoke(app, ["observe", "projects"])
    assert r.exit_code == 0
    assert "no projects" in r.stdout


def test_start_refuses_when_observe_is_empty(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    (tawn_home / "grants.yaml").write_text("read: []\nwrite: []\nobserve: []\n")
    r = runner.invoke(app, ["observe", "start"])
    assert r.exit_code == 1


def test_projects_lists_a_granted_repo(tawn_home, tmp_path):
    tawn_home.mkdir(parents=True, exist_ok=True)
    repo = tmp_path / "myproj"
    (repo / ".git").mkdir(parents=True)
    (tawn_home / "grants.yaml").write_text(
        f"read: [{repo}]\nwrite: []\nobserve: [fs]\n"
    )
    r = runner.invoke(app, ["observe", "projects"])
    assert r.exit_code == 0
    assert "myproj" in r.stdout
    assert "git" in r.stdout


def test_unknown_action_exits_nonzero(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    (tawn_home / "grants.yaml").write_text("read: []\nwrite: []\nobserve: []\n")
    r = runner.invoke(app, ["observe", "wat"])
    assert r.exit_code == 1
    assert "unknown action" in r.stdout
