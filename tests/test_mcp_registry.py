import yaml

from tawn.mcp.registry import (
    MCPServer, get_server, load_servers, remove_server, save_servers, upsert_server,
)


def _srv(name="github", **kw):
    base = dict(name=name, transport="stdio", command="npx", args=["-y", "srv"])
    base.update(kw)
    return MCPServer(**base)


def test_missing_file_yields_no_servers(tmp_path):
    assert load_servers(tmp_path) == []


def test_round_trip(tmp_path):
    save_servers(tmp_path, [_srv(), _srv("gmail", transport="http", url="http://x")])
    got = load_servers(tmp_path)
    assert [s.name for s in got] == ["github", "gmail"]
    assert got[1].url == "http://x"


def test_servers_default_to_disabled(tmp_path):
    """A server present in the file but with no `enabled` key must not be on.

    Defaulting the other way would make a hand-edited config silently
    callable.
    """
    path = tmp_path / "mcp" / "servers.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump({"servers": [{"name": "x", "transport": "stdio", "command": "c"}]})
    )
    assert load_servers(tmp_path)[0].enabled is False


def test_upsert_replaces_by_name_rather_than_appending(tmp_path):
    assert upsert_server(tmp_path, _srv()) is True
    assert upsert_server(tmp_path, _srv(enabled=True)) is False
    servers = load_servers(tmp_path)
    assert len(servers) == 1
    assert servers[0].enabled is True


def test_remove_reports_whether_it_removed_anything(tmp_path):
    upsert_server(tmp_path, _srv())
    assert remove_server(tmp_path, "nope") is False
    assert remove_server(tmp_path, "github") is True
    assert load_servers(tmp_path) == []


def test_get_server(tmp_path):
    upsert_server(tmp_path, _srv())
    assert get_server(tmp_path, "github").command == "npx"
    assert get_server(tmp_path, "absent") is None


def test_env_keys_are_names_only(tmp_path):
    upsert_server(tmp_path, _srv(env_keys=["GITHUB_TOKEN"]))
    text = (tmp_path / "mcp" / "servers.yaml").read_text()
    assert "GITHUB_TOKEN" in text
    assert load_servers(tmp_path)[0].env_keys == ["GITHUB_TOKEN"]
