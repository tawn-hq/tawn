"""MCP Manager — Tawn as an MCP *client* (design spec §7).

`tawn.mcp_server` is the other direction: Tawn's own verbs exposed to Claude
Code and Cursor. This package is what lets Tawn call *their* servers.
"""

from tawn.mcp.registry import (
    MCPServer,
    get_server,
    load_servers,
    remove_server,
    save_servers,
    upsert_server,
)

__all__ = [
    "MCPServer",
    "get_server",
    "load_servers",
    "remove_server",
    "save_servers",
    "upsert_server",
]
