import json

from tawn.mcp.adopt import adopt, config_path_for, discover_configured_servers
from tawn.mcp.registry import load_servers


def _claude(tmp_path, monkeypatch, payload):
    cfg = tmp_path / "claude.json"
    cfg.write_text(json.dumps(payload))
    monkeypatch.setenv("TAWN_MCP_CONFIG_CLAUDE_CODE", str(cfg))
    return cfg


def _isolate_others(tmp_path, monkeypatch):
    """Point every other tool at a nonexistent path.

    Without this the developer's real ~/.codex or ~/.gemini leaks into a test
    that is meant to see one config.
    """
    for tool in ("CODEX", "GEMINI_CLI", "CURSOR"):
        monkeypatch.setenv(f"TAWN_MCP_CONFIG_{tool}", str(tmp_path / "absent"))


def test_config_path_honours_the_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("TAWN_MCP_CONFIG_CLAUDE_CODE", str(tmp_path / "x.json"))
    assert config_path_for("claude-code") == tmp_path / "x.json"


def test_adopted_servers_are_written_disabled(tmp_path, monkeypatch):
    _isolate_others(tmp_path, monkeypatch)
    _claude(tmp_path, monkeypatch, {
        "mcpServers": {
            "github": {
                "command": "npx", "args": ["-y", "srv"],
                "env": {"GITHUB_TOKEN": "ghp_REALSECRET"},
            }
        }
    })
    found = discover_configured_servers()
    s = next(x for x in found if x.name == "github")
    assert s.enabled is False  # discovery is not consent
    assert s.source == "adopted:claude-code"
    assert s.env_keys == ["GITHUB_TOKEN"]
    # The secret's name travels; its value never does.
    assert "ghp_REALSECRET" not in s.model_dump_json()


def test_per_project_servers_are_found_too(tmp_path, monkeypatch):
    _isolate_others(tmp_path, monkeypatch)
    _claude(tmp_path, monkeypatch, {
        "mcpServers": {},
        "projects": {"/home/x/proj": {"mcpServers": {"local": {"command": "run"}}}},
    })
    assert "local" in {s.name for s in discover_configured_servers()}


def test_http_servers_keep_their_url(tmp_path, monkeypatch):
    _isolate_others(tmp_path, monkeypatch)
    _claude(tmp_path, monkeypatch, {"mcpServers": {"web": {"url": "https://x/mcp"}}})
    s = next(x for x in discover_configured_servers() if x.name == "web")
    assert s.transport == "http"
    assert s.url == "https://x/mcp"


def test_absent_config_contributes_nothing(tmp_path, monkeypatch):
    _isolate_others(tmp_path, monkeypatch)
    monkeypatch.setenv("TAWN_MCP_CONFIG_CLAUDE_CODE", str(tmp_path / "nope.json"))
    assert discover_configured_servers() == []


def test_malformed_config_is_skipped_not_raised(tmp_path, monkeypatch):
    _isolate_others(tmp_path, monkeypatch)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    monkeypatch.setenv("TAWN_MCP_CONFIG_CLAUDE_CODE", str(bad))
    assert discover_configured_servers() == []


def test_codex_toml_is_read(tmp_path, monkeypatch):
    _isolate_others(tmp_path, monkeypatch)
    monkeypatch.setenv("TAWN_MCP_CONFIG_CLAUDE_CODE", str(tmp_path / "absent"))
    cfg = tmp_path / "config.toml"
    cfg.write_text('[mcp_servers.fs]\ncommand = "npx"\nargs = ["-y", "fs"]\n')
    monkeypatch.setenv("TAWN_MCP_CONFIG_CODEX", str(cfg))
    s = next(x for x in discover_configured_servers() if x.name == "fs")
    assert s.source == "adopted:codex"
    assert s.args == ["-y", "fs"]


def test_adopt_writes_once(tmp_path, monkeypatch):
    _isolate_others(tmp_path, monkeypatch)
    _claude(tmp_path, monkeypatch, {"mcpServers": {"github": {"command": "npx"}}})
    home = tmp_path / "home"
    found = discover_configured_servers()
    assert adopt(home, found) == 1
    assert adopt(home, found) == 0
    assert len(load_servers(home)) == 1
    assert load_servers(home)[0].enabled is False
