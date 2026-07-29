from tawn.mcp import catalog as cat
from tawn.mcp.client import ServerHealth
from tawn.mcp.registry import MCPServer

SRV = MCPServer(name="github", transport="stdio", command="npx")
TOOLS = [{"name": "create_issue", "description": "d", "parameters": {"type": "object"}}]


def _ok(monkeypatch, tools=TOOLS):
    calls = []

    def _probe(server):
        calls.append(server.name)
        return ServerHealth(name=server.name, reachable=True,
                            tool_count=len(tools), tools=tools)

    monkeypatch.setattr(cat, "probe", _probe)
    return calls


def _down(monkeypatch):
    monkeypatch.setattr(
        cat, "probe",
        lambda s: ServerHealth(name=s.name, reachable=False, error="boom"),
    )


def test_first_fetch_is_live(tmp_path, monkeypatch):
    _ok(monkeypatch)
    tools, source = cat.get_tools(tmp_path, SRV, now=1000.0)
    assert source == "live"
    assert tools == TOOLS


def test_within_ttl_it_serves_cache_without_reconnecting(tmp_path, monkeypatch):
    calls = _ok(monkeypatch)
    cat.get_tools(tmp_path, SRV, now=1000.0)
    tools, source = cat.get_tools(tmp_path, SRV, now=1000.0 + 60)
    assert source == "cache"
    assert tools == TOOLS
    assert len(calls) == 1  # the second call never touched the server


def test_after_ttl_it_refetches(tmp_path, monkeypatch):
    calls = _ok(monkeypatch)
    cat.get_tools(tmp_path, SRV, now=1000.0)
    _, source = cat.get_tools(tmp_path, SRV, now=1000.0 + cat.CACHE_TTL_SECONDS + 1)
    assert source == "live"
    assert len(calls) == 2


def test_refresh_forces_a_refetch(tmp_path, monkeypatch):
    calls = _ok(monkeypatch)
    cat.get_tools(tmp_path, SRV, now=1000.0)
    cat.get_tools(tmp_path, SRV, refresh=True, now=1000.0 + 1)
    assert len(calls) == 2


def test_unreachable_with_a_cache_serves_it_as_stale(tmp_path, monkeypatch):
    _ok(monkeypatch)
    cat.get_tools(tmp_path, SRV, now=1000.0)
    _down(monkeypatch)
    tools, source = cat.get_tools(tmp_path, SRV, refresh=True, now=1000.0 + 1)
    # A stale list beats no list, but it must announce itself.
    assert source == "stale"
    assert tools == TOOLS


def test_unreachable_with_no_cache_is_empty_and_stale(tmp_path, monkeypatch):
    _down(monkeypatch)
    tools, source = cat.get_tools(tmp_path, SRV, now=1000.0)
    assert (tools, source) == ([], "stale")


def test_cached_tools_does_not_connect(tmp_path, monkeypatch):
    _ok(monkeypatch)
    cat.get_tools(tmp_path, SRV, now=1000.0)
    monkeypatch.setattr(
        cat, "probe",
        lambda s: (_ for _ in ()).throw(AssertionError("must not connect")),
    )
    assert cat.cached_tools(tmp_path, "github") == TOOLS
    assert cat.cached_tools(tmp_path, "absent") == []


def test_forget_drops_one_server(tmp_path, monkeypatch):
    _ok(monkeypatch)
    cat.get_tools(tmp_path, SRV, now=1000.0)
    cat.forget(tmp_path, "github")
    assert cat.cached_tools(tmp_path, "github") == []
