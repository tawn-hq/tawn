import json

import pytest

from tawn.capability.grants import Grants
from tawn.mcp.registry import MCPServer, upsert_server
from tawn.model.tools import MANAGE_SOURCE, ToolRegistry, _assert_no_enable
from tawn.model.types import ToolCall, ToolSpec


def _catalog(home, server="github", tools=None):
    import json as _json

    path = home / "mcp" / "catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps({server: {"fetched_at": 1e12, "tools": tools or [
        {"name": "create_issue", "description": "d", "parameters": {"type": "object"}}
    ]}}))


def test_tawn_verbs_are_always_available(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    reg = ToolRegistry.build(tawn_home, Grants())
    assert {"recall", "note", "brief"} <= reg.names()


def test_a_server_enabled_but_ungranted_is_not_callable(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    upsert_server(tawn_home, MCPServer(name="github", command="npx", enabled=True))
    _catalog(tawn_home)
    reg = ToolRegistry.build(tawn_home, Grants(mcp=[]))
    assert reg.get("github__create_issue") is None


def test_a_server_granted_but_disabled_is_not_callable(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    upsert_server(tawn_home, MCPServer(name="github", command="npx", enabled=False))
    _catalog(tawn_home)
    reg = ToolRegistry.build(tawn_home, Grants(mcp=["github"]))
    assert reg.get("github__create_issue") is None


def test_both_gates_open_makes_it_callable(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    upsert_server(tawn_home, MCPServer(name="github", command="npx", enabled=True))
    _catalog(tawn_home)
    reg = ToolRegistry.build(tawn_home, Grants(mcp=["github"]))
    spec = reg.get("github__create_issue")
    assert spec is not None
    assert spec.source == "mcp:github"


def test_management_tools_are_exposed(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    reg = ToolRegistry.build(tawn_home, Grants())
    manage = {s.name for s in reg.specs() if s.source == MANAGE_SOURCE}
    assert {"mcp_add", "mcp_adopt", "skill_new", "tool_new"} <= manage


def test_no_management_tool_can_flip_enabled_state(tawn_home):
    """Staging is delegable; enabling is not.

    A model that could enable what it just registered would grant itself a
    capability inside one turn, making disabled-by-default decorative.
    """
    tawn_home.mkdir(parents=True, exist_ok=True)
    reg = ToolRegistry.build(tawn_home, Grants())
    names = {s.name for s in reg.specs() if s.source == MANAGE_SOURCE}
    assert not any("enable" in n or "grant" in n for n in names)


def test_the_guard_rejects_an_enable_tool(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    reg = ToolRegistry(tawn_home)
    reg.register(
        ToolSpec(name="mcp_enable", description="d", parameters={}, source=MANAGE_SOURCE),
        lambda: "x",
    )
    with pytest.raises(RuntimeError, match="grant itself"):
        _assert_no_enable(reg)


def test_mcp_add_via_the_model_writes_a_disabled_server(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    reg = ToolRegistry.build(tawn_home, Grants())
    out = reg.execute(ToolCall(id="1", name="mcp_add",
                               arguments={"name": "fs", "command": "npx"}))
    assert out.is_error is False
    assert "disabled" in out.content
    from tawn.mcp.registry import get_server
    assert get_server(tawn_home, "fs").enabled is False


def test_unknown_tool_is_an_error_result_not_an_exception(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    reg = ToolRegistry.build(tawn_home, Grants())
    out = reg.execute(ToolCall(id="1", name="nope"))
    assert out.is_error is True
    assert "no such tool" in out.content


def test_a_raising_tool_becomes_an_error_result(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    reg = ToolRegistry(tawn_home)

    def _boom():
        raise ValueError("kaboom")

    reg.register(ToolSpec(name="boom", description="d", parameters={}), _boom)
    out = reg.execute(ToolCall(id="1", name="boom"))
    assert out.is_error is True
    assert "kaboom" in out.content


def test_audit_records_arg_keys_never_values(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    reg = ToolRegistry(tawn_home)
    reg.register(ToolSpec(name="t", description="d", parameters={}), lambda **k: "ok")
    reg.execute(ToolCall(id="1", name="t", arguments={"token": "SUPERSECRET"}))

    from tawn.capability.audit import AuditLog, audit_path

    entries = AuditLog(audit_path(tawn_home)).entries()
    blob = json.dumps(entries)
    assert "token" in blob
    assert "SUPERSECRET" not in blob
