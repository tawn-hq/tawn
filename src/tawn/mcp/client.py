"""Connecting to MCP servers.

fastmcp's client is async and every Tawn caller (CLI, agent loop, routes) is
sync, so a session owns a background event loop thread and marshals coroutines
onto it. The alternative — `asyncio.run` per operation — would reconnect on
every call, and for a stdio server that means spawning `npx` again each time.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tawn.mcp.registry import MCPServer


class MCPUnavailable(RuntimeError):
    """fastmcp is not installed, or the server could not be reached."""


def client_config(server: MCPServer) -> dict:
    """The standard MCP config block for one server.

    Secrets are resolved here, at connect time, from the OS keyring — never
    read from or written to the registry file.
    """
    entry: dict[str, Any] = {}
    if server.transport == "http":
        entry["url"] = server.url
    else:
        entry["command"] = server.command
        if server.args:
            entry["args"] = list(server.args)
    env = {}
    for key in server.env_keys:
        value = _secret(key)
        if value:
            env[key] = value
    if env:
        entry["env"] = env
    return {"mcpServers": {server.name: entry}}


def _secret(key: str) -> str | None:
    import os

    value = os.environ.get(key)
    if value:
        return value
    try:
        import keyring

        return keyring.get_password("tawn", key)
    except Exception:
        return None


class _LoopThread:
    """A background event loop that outlives individual calls."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run, name="tawn-mcp-loop", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro, timeout: float = 60.0):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def shutdown(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)


class MCPSession:
    """A live connection to one MCP server."""

    def __init__(self, server: MCPServer):
        self.server = server
        self._loop = _LoopThread()
        try:
            from fastmcp import Client
        except ImportError as exc:  # pragma: no cover - fastmcp is a hard dep
            self._loop.shutdown()
            raise MCPUnavailable(f"fastmcp not installed: {exc}") from exc

        self._client = Client(client_config(server))
        try:
            self._loop.submit(self._client.__aenter__())
        except Exception as exc:
            self._loop.shutdown()
            raise MCPUnavailable(str(exc)) from exc

    def list_tools(self) -> list[dict]:
        tools = self._loop.submit(self._client.list_tools())
        out = []
        for t in tools:
            out.append(
                {
                    "name": t.name,
                    "description": getattr(t, "description", "") or "",
                    "parameters": getattr(t, "inputSchema", None)
                    or {"type": "object", "properties": {}},
                }
            )
        return out

    def call_tool(self, name: str, args: dict) -> str:
        result = self._loop.submit(self._client.call_tool(name, args))
        content = getattr(result, "content", result)
        if isinstance(content, list):
            return "\n".join(
                getattr(part, "text", str(part)) for part in content
            )
        return str(content)

    def close(self) -> None:
        try:
            self._loop.submit(self._client.__aexit__(None, None, None), timeout=10)
        except Exception:
            pass
        self._loop.shutdown()


def connect(server: MCPServer) -> MCPSession:
    return MCPSession(server)


@dataclass
class ServerHealth:
    name: str
    reachable: bool
    error: str | None = None
    tool_count: int = 0
    tools: list[dict] = field(default_factory=list)


def probe(server: MCPServer) -> ServerHealth:
    """Connect, list tools, disconnect.

    A server that is down and a server that was never configured must not look
    the same, so the error is preserved rather than collapsed into an empty
    result.
    """
    session = None
    try:
        session = connect(server)
        tools = session.list_tools()
        return ServerHealth(
            name=server.name, reachable=True, tool_count=len(tools), tools=tools
        )
    except Exception as exc:
        return ServerHealth(name=server.name, reachable=False, error=str(exc))
    finally:
        if session is not None:
            session.close()
