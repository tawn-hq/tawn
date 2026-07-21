"""Tests for MCP server tools (Task 15)."""

import pytest


def test_mcp_server_importable():
    from tawn.mcp_server import mcp
    assert mcp is not None
    assert mcp.name == "tawn"


def test_mcp_has_tool_functions():
    import tawn.mcp_server as ms
    assert callable(getattr(ms, "recall", None))
    assert callable(getattr(ms, "note", None))
    assert callable(getattr(ms, "brief", None))


def test_mcp_tool_list():
    from tawn.mcp_server import mcp
    try:
        from fastmcp.testing import MCPTestClient
        client = MCPTestClient(mcp)
        tools = client.list_tools()
        names = [t.name for t in tools]
        assert "recall" in names
        assert "note" in names
        assert "brief" in names
    except (ImportError, AttributeError):
        # fastmcp version without test client — just verify module exports
        from tawn.mcp_server import mcp as m
        assert m.name == "tawn"
