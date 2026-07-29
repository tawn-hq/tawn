"""/api/tools — MCP servers, skills, generated tools."""

import pytest
from fastapi.testclient import TestClient

from tawn.mcp.registry import MCPServer, get_server, upsert_server
from tawn.skills.store import SKILL_FILE, Skill, get_skill, save_skill
from tawn.tools.creator import read_manifest, write_tool

SAFE = "def run(x: str) -> str:\n    return x.upper()\n"


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    for agent in ("CLAUDE_CODE", "CURSOR", "GEMINI_CLI", "CODEX"):
        monkeypatch.setenv(f"TAWN_SKILLS_DIR_{agent}", str(tmp_path / "absent" / agent))
        monkeypatch.setenv(f"TAWN_MCP_CONFIG_{agent}", str(tmp_path / "absent.json"))
    monkeypatch.setenv("TAWN_SKILLS_PLUGIN_GLOB", str(tmp_path / "none" / "*.md"))


@pytest.fixture
def client(tawn_home, db_engine):
    tawn_home.mkdir(parents=True, exist_ok=True)
    (tawn_home / "grants.yaml").write_text(
        "read: []\nwrite: []\nobserve: []\nmcp: []\nnet: false\n"
    )
    from tawn.web import create_app

    return TestClient(create_app(db_engine))


def _grant_mcp(tawn_home, *names):
    (tawn_home / "grants.yaml").write_text(
        f"read: []\nwrite: []\nobserve: []\nmcp: [{', '.join(names)}]\nnet: false\n"
    )


# ── MCP servers ──────────────────────────────────────────────────────────────

def test_an_empty_registry(client):
    assert client.get("/api/tools/mcp/servers").json()["servers"] == []


def test_adding_a_server_leaves_it_disabled(client, tawn_home):
    r = client.post("/api/tools/mcp/servers",
                    json={"name": "fs", "command": "npx", "args": ["-y", "fs"]})
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert get_server(tawn_home, "fs").enabled is False


def test_the_two_gates_are_reported_separately(client, tawn_home):
    """The UI has to be able to say *which* gate is closed."""
    upsert_server(tawn_home, MCPServer(name="github", command="npx", enabled=True))
    row = client.get("/api/tools/mcp/servers").json()["servers"][0]
    assert row["enabled"] is True
    assert row["granted"] is False
    assert row["callable"] is False

    _grant_mcp(tawn_home, "github")
    row = client.get("/api/tools/mcp/servers").json()["servers"][0]
    assert row["callable"] is True


def test_enabling_reports_that_it_is_still_ungranted(client, tawn_home):
    upsert_server(tawn_home, MCPServer(name="fs", command="npx"))
    body = client.post("/api/tools/mcp/fs/enable").json()
    assert body["enabled"] is True
    assert body["granted"] is False
    assert body["callable"] is False


def test_acting_on_an_absent_server(client):
    assert client.post("/api/tools/mcp/ghost/enable").json()["ok"] is False


def test_removing_a_server(client, tawn_home):
    upsert_server(tawn_home, MCPServer(name="fs", command="npx"))
    assert client.post("/api/tools/mcp/fs/remove").json()["ok"] is True
    assert get_server(tawn_home, "fs") is None


def test_discovery_marks_what_is_already_known(client, tawn_home, tmp_path, monkeypatch):
    import json

    cfg = tmp_path / "claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"github": {"command": "npx"}}}))
    monkeypatch.setenv("TAWN_MCP_CONFIG_CLAUDE_CODE", str(cfg))

    rows = client.get("/api/tools/mcp/discovered").json()["servers"]
    assert rows[0]["known"] is False
    assert client.post("/api/tools/mcp/adopt").json()["added"] == 1
    assert client.get("/api/tools/mcp/discovered").json()["servers"][0]["known"] is True
    assert get_server(tawn_home, "github").enabled is False


# ── skills ───────────────────────────────────────────────────────────────────

def test_listing_and_saving_skills(client, tawn_home):
    assert client.get("/api/tools/skills").json()["skills"] == []
    client.post("/api/tools/skills",
                json={"name": "review", "description": "d", "body": "Body."})
    skills = client.get("/api/tools/skills").json()["skills"]
    assert skills[0]["name"] == "review"
    assert skills[0]["body"] == "Body."


def test_deleting_a_skill(client, tawn_home):
    save_skill(tawn_home, Skill(name="review", description="d", body="B"))
    assert client.delete("/api/tools/skills/review").json()["ok"] is True
    assert get_skill(tawn_home, "review") is None


def test_syncing_reports_targets(client, tawn_home, tmp_path, monkeypatch):
    target = tmp_path / "claude"
    target.mkdir()
    monkeypatch.setenv("TAWN_SKILLS_DIR_CLAUDE_CODE", str(target))
    save_skill(tawn_home, Skill(name="review", description="d", body="B"))

    body = client.post("/api/tools/skills/sync").json()
    assert body["written"] == ["claude-code/review"]
    assert (target / "review" / SKILL_FILE).is_file()


def test_import_defaults_to_a_dry_run(client, tawn_home, tmp_path, monkeypatch):
    """The safe default: the UI shows what *would* happen first."""
    source = tmp_path / "claude"
    (source / "caveman").mkdir(parents=True)
    (source / "caveman" / SKILL_FILE).write_text(
        "---\nname: caveman\ndescription: d\n---\n\nTerse.\n"
    )
    monkeypatch.setenv("TAWN_SKILLS_DIR_CLAUDE_CODE", str(source))

    body = client.post("/api/tools/skills/import").json()
    assert body["dry_run"] is True
    assert body["imported"] == ["caveman"]
    assert get_skill(tawn_home, "caveman") is None

    client.post("/api/tools/skills/import?dry_run=false")
    assert get_skill(tawn_home, "caveman") is not None


# ── generated tools ──────────────────────────────────────────────────────────

def test_listing_generated_tools_reports_both_gates(client, tawn_home):
    src = "import httpx\ndef run(u): return httpx.get(u).text\n"
    write_tool(tawn_home, "fetch", {"name": "fetch", "capabilities": ["net"]}, src)
    row = client.get("/api/tools/generated").json()["tools"][0]
    assert row["enabled"] is False
    assert row["granted"] is False  # net: false
    assert row["capabilities"] == ["net"]


def test_showing_a_tool_returns_its_source_for_review(client, tawn_home):
    write_tool(tawn_home, "shout", {"name": "shout", "capabilities": []}, SAFE)
    body = client.get("/api/tools/generated/shout").json()
    assert body["ok"] is True
    assert "def run" in body["source"]
    assert body["manifest"]["enabled"] is False


def test_showing_an_absent_tool(client):
    assert client.get("/api/tools/generated/ghost").json()["ok"] is False


def test_generating_produces_a_disabled_tool(client, tawn_home, monkeypatch):
    import json

    payload = json.dumps({
        "name": "shout", "description": "Uppercase.",
        "parameters": {"type": "object", "properties": {}},
        "capabilities": [], "impl": SAFE, "test": "",
    })

    class Router:
        def complete(self, msgs, sensitive=True):
            class R:
                text = payload

            return R()

    monkeypatch.setattr("tawn.model.router.default_router", lambda home: Router())
    body = client.post("/api/tools/generated", json={"description": "uppercase"}).json()
    assert body["ok"] is True
    assert body["enabled"] is False
    assert read_manifest(tawn_home, "shout")["enabled"] is False


def test_a_capability_mismatch_is_reported_and_nothing_written(client, tawn_home, monkeypatch):
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
    body = client.post("/api/tools/generated", json={"description": "list files"}).json()
    assert body["ok"] is False
    assert body["kind"] == "capability_mismatch"
    assert read_manifest(tawn_home, "sneaky") is None


def test_enabling_a_generated_tool(client, tawn_home):
    write_tool(tawn_home, "shout", {"name": "shout", "capabilities": []}, SAFE)
    assert client.post("/api/tools/generated/shout/enable").json()["enabled"] is True
    assert read_manifest(tawn_home, "shout")["enabled"] is True
    assert client.post("/api/tools/generated/shout/disable").json()["enabled"] is False


def test_running_a_generated_tools_test(client, tawn_home):
    write_tool(
        tawn_home, "shout", {"name": "shout", "capabilities": []}, SAFE,
        test="def test_smoke():\n    assert True\n",
    )
    assert client.post("/api/tools/generated/shout/test").json()["ok"] is True


def test_removing_a_generated_tool(client, tawn_home):
    write_tool(tawn_home, "shout", {"name": "shout", "capabilities": []}, SAFE)
    assert client.post("/api/tools/generated/shout/remove").json()["ok"] is True
    assert read_manifest(tawn_home, "shout") is None
