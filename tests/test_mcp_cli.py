import json

from typer.testing import CliRunner

from tawn.cli import app
from tawn.mcp.registry import MCPServer, get_server, upsert_server

runner = CliRunner()


def _isolate(tmp_path, monkeypatch):
    for tool in ("CLAUDE_CODE", "CODEX", "GEMINI_CLI", "CURSOR"):
        monkeypatch.setenv(f"TAWN_MCP_CONFIG_{tool}", str(tmp_path / "absent"))


def _grants(home, mcp="[]"):
    home.mkdir(parents=True, exist_ok=True)
    (home / "grants.yaml").write_text(f"read: []\nwrite: []\nobserve: []\nmcp: {mcp}\n")


def test_bare_mcp_still_starts_the_server(tawn_home, monkeypatch):
    """Existing claude.json entries invoke `tawn mcp` with no argument."""
    _grants(tawn_home)
    started = []
    import tawn.mcp_server as srv

    monkeypatch.setattr(srv.mcp, "run", lambda **kw: started.append(kw))
    r = runner.invoke(app, ["mcp"])
    assert r.exit_code == 0
    assert started == [{"transport": "stdio"}]


def test_serve_is_the_same_path(tawn_home, monkeypatch):
    _grants(tawn_home)
    started = []
    import tawn.mcp_server as srv

    monkeypatch.setattr(srv.mcp, "run", lambda **kw: started.append(kw))
    assert runner.invoke(app, ["mcp", "serve"]).exit_code == 0
    assert started == [{"transport": "stdio"}]


def test_list_on_an_empty_registry_points_at_adopt(tawn_home):
    _grants(tawn_home)
    r = runner.invoke(app, ["mcp", "list"])
    assert r.exit_code == 0
    assert "tawn mcp adopt" in r.stdout


def test_list_shows_the_grant_gate_separately_from_enabled(tawn_home):
    _grants(tawn_home, mcp="[github]")
    upsert_server(tawn_home, MCPServer(name="github", command="npx", enabled=True))
    upsert_server(tawn_home, MCPServer(name="other", command="npx", enabled=True))
    r = runner.invoke(app, ["mcp", "list"])
    assert "github" in r.stdout and "granted" in r.stdout
    assert "not granted" in r.stdout  # `other` is enabled but ungranted


def test_add_writes_a_disabled_server(tawn_home):
    _grants(tawn_home)
    r = runner.invoke(app, ["mcp", "add", "fs", "--command", "npx", "--args", "-y fs"])
    assert r.exit_code == 0
    s = get_server(tawn_home, "fs")
    assert s.enabled is False
    assert s.args == ["-y", "fs"]


def test_add_without_command_or_url_fails(tawn_home):
    _grants(tawn_home)
    assert runner.invoke(app, ["mcp", "add", "fs"]).exit_code == 1


def test_enable_unknown_server_exits_nonzero(tawn_home):
    _grants(tawn_home)
    r = runner.invoke(app, ["mcp", "enable", "ghost"])
    assert r.exit_code == 1
    assert "no such server" in r.stdout


def test_enabling_an_ungranted_server_says_it_is_still_not_callable(tawn_home):
    _grants(tawn_home, mcp="[]")
    upsert_server(tawn_home, MCPServer(name="fs", command="npx"))
    r = runner.invoke(app, ["mcp", "enable", "fs"])
    assert r.exit_code == 0
    assert get_server(tawn_home, "fs").enabled is True
    assert "cannot be called" in r.stdout


def test_remove(tawn_home):
    _grants(tawn_home)
    upsert_server(tawn_home, MCPServer(name="fs", command="npx"))
    assert "removed fs" in runner.invoke(app, ["mcp", "remove", "fs"]).stdout
    assert "no such server" in runner.invoke(app, ["mcp", "remove", "fs"]).stdout


def test_adopt_writes_disabled_and_says_what_is_needed(tawn_home, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _grants(tawn_home)
    cfg = tmp_path / "claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"github": {"command": "npx"}}}))
    monkeypatch.setenv("TAWN_MCP_CONFIG_CLAUDE_CODE", str(cfg))
    r = runner.invoke(app, ["mcp", "adopt"])
    assert r.exit_code == 0
    assert "1 added, disabled" in r.stdout
    assert "grants.yaml" in r.stdout
    assert get_server(tawn_home, "github").enabled is False


def test_adopt_with_nothing_configured(tawn_home, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _grants(tawn_home)
    assert "no MCP servers found" in runner.invoke(app, ["mcp", "adopt"]).stdout


def test_unknown_action_exits_nonzero(tawn_home):
    _grants(tawn_home)
    r = runner.invoke(app, ["mcp", "wat"])
    assert r.exit_code == 1
    assert "unknown action" in r.stdout
