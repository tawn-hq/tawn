"""Finding MCP servers other tools have already configured.

Reading another tool's config tells Tawn a server *exists*. It does not tell
Tawn it may run it, so adoption always writes a disabled entry and never copies
a secret value — only the name of the environment variable holding it.
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

from tawn.mcp.registry import MCPServer, load_servers, upsert_server

#: Where each tool keeps its MCP configuration.
CONFIG_PATHS: dict[str, str] = {
    "claude-code": "~/.claude.json",
    "codex": "~/.codex/config.toml",
    "gemini-cli": "~/.gemini/settings.json",
    "cursor": "~/.cursor/mcp.json",
}


def _env_var(tool: str) -> str:
    return f"TAWN_MCP_CONFIG_{tool.upper().replace('-', '_')}"


def config_path_for(tool: str) -> Path:
    """The config path for a tool, honouring its env override.

    The override is the same isolation knob federation discovery uses, so a
    developer's real ~/.claude.json cannot leak into a test that expects none.
    """
    override = os.environ.get(_env_var(tool))
    if override:
        return Path(override)
    return Path(CONFIG_PATHS[tool]).expanduser()


def _server_from_entry(name: str, entry: dict, tool: str) -> MCPServer:
    url = entry.get("url") or entry.get("httpUrl")
    return MCPServer(
        name=name,
        transport="http" if url else "stdio",
        command=entry.get("command"),
        args=list(entry.get("args") or []),
        url=url,
        # Names only. Copying the values would move another tool's secrets into
        # a file the user did not choose to put them in.
        env_keys=sorted((entry.get("env") or {}).keys()),
        enabled=False,
        source=f"adopted:{tool}",
    )


def _from_json(path: Path, tool: str) -> list[MCPServer]:
    data = json.loads(path.read_text())
    blocks: list[dict] = [data.get("mcpServers") or {}]
    # Claude Code also scopes servers per project.
    for project in (data.get("projects") or {}).values():
        if isinstance(project, dict) and project.get("mcpServers"):
            blocks.append(project["mcpServers"])
    out: list[MCPServer] = []
    seen: set[str] = set()
    for block in blocks:
        for name, entry in block.items():
            if name in seen or not isinstance(entry, dict):
                continue
            seen.add(name)
            out.append(_server_from_entry(name, entry, tool))
    return out


def _from_toml(path: Path, tool: str) -> list[MCPServer]:
    data = tomllib.loads(path.read_text())
    block = data.get("mcp_servers") or data.get("mcpServers") or {}
    return [
        _server_from_entry(name, entry, tool)
        for name, entry in block.items()
        if isinstance(entry, dict)
    ]


def discover_configured_servers() -> list[MCPServer]:
    """Every MCP server another tool on this machine already has configured."""
    out: list[MCPServer] = []
    for tool in CONFIG_PATHS:
        path = config_path_for(tool)
        if not path.is_file():
            continue
        try:
            parsed = (
                _from_toml(path, tool)
                if path.suffix == ".toml"
                else _from_json(path, tool)
            )
        except Exception:
            # One unparseable config must not hide the others.
            continue
        out.extend(parsed)
    return out


def adopt(home: Path, servers: list[MCPServer]) -> int:
    """Write discovered servers into the registry. Returns how many were new.

    Existing entries are left alone: re-running adoption must not silently
    revert a server the user enabled.
    """
    known = {s.name for s in load_servers(home)}
    written = 0
    for server in servers:
        if server.name in known:
            continue
        upsert_server(home, server)
        known.add(server.name)
        written += 1
    return written
