"""CLI for skills and generated tools."""

import pytest
from typer.testing import CliRunner

from tawn.cli import app
from tawn.skills.store import SKILL_FILE, Skill, get_skill, save_skill
from tawn.tools.creator import read_manifest, write_tool

runner = CliRunner()
SAFE = "def run(x: str) -> str:\n    return x.upper()\n"


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    for agent in ("CLAUDE_CODE", "CURSOR", "GEMINI_CLI", "CODEX"):
        monkeypatch.setenv(f"TAWN_SKILLS_DIR_{agent}", str(tmp_path / "absent" / agent))
    monkeypatch.setenv("TAWN_SKILLS_PLUGIN_GLOB", str(tmp_path / "none" / "*.md"))


def _home(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    (tawn_home / "grants.yaml").write_text("read: []\nwrite: []\nobserve: []\nmcp: []\n")
    return tawn_home


# ── skills ───────────────────────────────────────────────────────────────────

def test_an_empty_store_suggests_the_next_step(tawn_home):
    _home(tawn_home)
    r = runner.invoke(app, ["skill", "list"])
    assert r.exit_code == 0
    assert "tawn skill new" in r.stdout


def test_new_scaffolds_without_a_model(tawn_home, monkeypatch):
    """A missing model must not block authoring."""
    _home(tawn_home)

    def _boom(home):
        raise RuntimeError("no provider configured")

    monkeypatch.setattr("tawn.model.router.default_router", _boom)
    r = runner.invoke(app, ["skill", "new", "review", "-d", "review my PRs"])
    assert r.exit_code == 0
    assert get_skill(tawn_home, "review") is not None


def test_new_uses_the_model_when_one_exists(tawn_home, monkeypatch):
    _home(tawn_home)

    class R:
        text = "Step 1. Read the diff.\nStep 2. Say what is wrong."

    class Router:
        def complete(self, msgs, sensitive=True):
            return R()

    monkeypatch.setattr("tawn.model.router.default_router", lambda home: Router())
    runner.invoke(app, ["skill", "new", "review", "-d", "review my PRs"])
    assert "Read the diff" in get_skill(tawn_home, "review").body


def test_show_and_remove(tawn_home):
    _home(tawn_home)
    save_skill(tawn_home, Skill(name="review", description="d", body="Body."))
    assert "Body." in runner.invoke(app, ["skill", "show", "review"]).stdout
    assert "removed" in runner.invoke(app, ["skill", "remove", "review"]).stdout
    assert runner.invoke(app, ["skill", "show", "review"]).exit_code == 1


def test_sync_reports_where_it_wrote(tawn_home, tmp_path, monkeypatch):
    _home(tawn_home)
    target = tmp_path / "claude"
    target.mkdir()
    monkeypatch.setenv("TAWN_SKILLS_DIR_CLAUDE_CODE", str(target))
    save_skill(tawn_home, Skill(name="review", description="d", body="Body."))

    r = runner.invoke(app, ["skill", "sync"])
    assert r.exit_code == 0
    assert "claude-code/review" in r.stdout
    assert (target / "review" / SKILL_FILE).is_file()


def test_sync_with_no_agents_says_so(tawn_home):
    _home(tawn_home)
    save_skill(tawn_home, Skill(name="review", description="d", body="Body."))
    assert "no agents detected" in runner.invoke(app, ["skill", "sync"]).stdout


def test_import_dry_run_writes_nothing(tawn_home, tmp_path, monkeypatch):
    _home(tawn_home)
    source = tmp_path / "claude"
    (source / "caveman").mkdir(parents=True)
    (source / "caveman" / SKILL_FILE).write_text(
        "---\nname: caveman\ndescription: d\n---\n\nTerse.\n"
    )
    monkeypatch.setenv("TAWN_SKILLS_DIR_CLAUDE_CODE", str(source))

    r = runner.invoke(app, ["skill", "import", "--dry-run"])
    assert "would import" in r.stdout
    assert "nothing was written" in r.stdout
    assert get_skill(tawn_home, "caveman") is None

    runner.invoke(app, ["skill", "import"])
    assert get_skill(tawn_home, "caveman") is not None


def test_unknown_skill_action_exits_nonzero(tawn_home):
    _home(tawn_home)
    r = runner.invoke(app, ["skill", "wat"])
    assert r.exit_code == 1
    assert "unknown action" in r.stdout


# ── tools ────────────────────────────────────────────────────────────────────

def test_an_empty_tool_store_suggests_the_next_step(tawn_home):
    _home(tawn_home)
    assert "tawn tool new" in runner.invoke(app, ["tool", "list"]).stdout


def test_list_shows_enabled_state_and_capabilities(tawn_home):
    _home(tawn_home)
    write_tool(tawn_home, "shout", {"name": "shout", "capabilities": ["read"]}, SAFE)
    out = runner.invoke(app, ["tool", "list"]).stdout
    assert "shout" in out
    assert "off" in out
    assert "read" in out


def test_new_writes_a_disabled_tool_and_says_how_to_review(tawn_home, monkeypatch):
    _home(tawn_home)
    import json

    payload = json.dumps({
        "name": "shout", "description": "Uppercase.",
        "parameters": {"type": "object", "properties": {"x": {"type": "string"}}},
        "capabilities": [], "impl": SAFE, "test": "def test_x():\n    assert True\n",
    })

    class R:
        text = payload

    class Router:
        def complete(self, msgs, sensitive=True):
            return R()

    monkeypatch.setattr("tawn.model.router.default_router", lambda home: Router())
    r = runner.invoke(app, ["tool", "new", "uppercase a string"])
    assert r.exit_code == 0
    assert "DISABLED" in r.stdout
    assert "tawn tool show shout" in r.stdout
    assert read_manifest(tawn_home, "shout")["enabled"] is False


def test_new_reports_a_capability_mismatch_rather_than_writing(tawn_home, monkeypatch):
    _home(tawn_home)
    import json

    payload = json.dumps({
        "name": "sneaky", "description": "d", "parameters": {},
        "capabilities": [],
        "impl": "import subprocess\ndef run(): subprocess.run(['ls'])\n",
    })

    class Router:
        def complete(self, msgs, sensitive=True):
            class R:
                text = payload

            return R()

    monkeypatch.setattr("tawn.model.router.default_router", lambda home: Router())
    r = runner.invoke(app, ["tool", "new", "list files"])
    assert r.exit_code == 1
    assert "rejected" in r.stdout
    assert read_manifest(tawn_home, "sneaky") is None


def test_show_prints_the_manifest_and_the_source(tawn_home):
    _home(tawn_home)
    write_tool(tawn_home, "shout", {"name": "shout", "capabilities": []}, SAFE)
    out = runner.invoke(app, ["tool", "show", "shout"]).stdout
    assert "enabled: false" in out
    assert "def run" in out


def test_enable_warns_about_the_capabilities_it_needs(tawn_home):
    _home(tawn_home)
    src = "import httpx\ndef run(u): return httpx.get(u).text\n"
    write_tool(tawn_home, "fetch", {"name": "fetch", "capabilities": ["net"]}, src)
    out = runner.invoke(app, ["tool", "enable", "fetch"]).stdout
    assert "enabled" in out
    assert "net" in out
    assert read_manifest(tawn_home, "fetch")["enabled"] is True


def test_enable_on_an_absent_tool_exits_nonzero(tawn_home):
    _home(tawn_home)
    assert runner.invoke(app, ["tool", "enable", "ghost"]).exit_code == 1


def test_test_runs_the_generated_smoke_test(tawn_home):
    _home(tawn_home)
    write_tool(
        tawn_home, "shout", {"name": "shout", "capabilities": []}, SAFE,
        test="def test_smoke():\n    assert True\n",
    )
    assert runner.invoke(app, ["tool", "test", "shout"]).exit_code == 0


def test_remove(tawn_home):
    _home(tawn_home)
    write_tool(tawn_home, "shout", {"name": "shout", "capabilities": []}, SAFE)
    assert "removed" in runner.invoke(app, ["tool", "remove", "shout"]).stdout
    assert "no tool named" in runner.invoke(app, ["tool", "remove", "shout"]).stdout


def test_unknown_tool_action_exits_nonzero(tawn_home):
    _home(tawn_home)
    assert runner.invoke(app, ["tool", "wat"]).exit_code == 1
