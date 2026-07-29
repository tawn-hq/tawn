"""The MCP server registry — what Tawn knows how to connect to.

Stored at `~/.tawn/mcp/servers.yaml`. Holds definitions only: `env_keys` names
the environment variables a server wants, never their values. Secrets stay in
the OS keyring, as API keys already do — a config file that is safe to read is
worth more than one that is convenient to write.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_REL = "mcp/servers.yaml"


class MCPServer(BaseModel):
    name: str
    transport: str = "stdio"  # stdio | http
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    #: Names of environment variables the server needs. Never values.
    env_keys: list[str] = Field(default_factory=list)
    #: Deliberately False by default: a hand-edited config that omits this key
    #: must not become silently callable.
    enabled: bool = False
    source: str = "manual"  # manual | adopted:<tool>


def _path(home: Path) -> Path:
    return Path(home) / _REL


def load_servers(home: Path) -> list[MCPServer]:
    path = _path(home)
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return []
    return [MCPServer.model_validate(s) for s in (data.get("servers") or [])]


def save_servers(home: Path, servers: list[MCPServer]) -> None:
    path = _path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"servers": [s.model_dump(exclude_none=True) for s in servers]},
            sort_keys=False,
        )
    )


def get_server(home: Path, name: str) -> MCPServer | None:
    return next((s for s in load_servers(home) if s.name == name), None)


def upsert_server(home: Path, server: MCPServer) -> bool:
    """Add or replace by name. Returns True when the server was new."""
    servers = load_servers(home)
    for i, existing in enumerate(servers):
        if existing.name == server.name:
            servers[i] = server
            save_servers(home, servers)
            return False
    servers.append(server)
    save_servers(home, servers)
    return True


def remove_server(home: Path, name: str) -> bool:
    """Returns True when something was actually removed."""
    servers = load_servers(home)
    kept = [s for s in servers if s.name != name]
    if len(kept) == len(servers):
        return False
    save_servers(home, kept)
    return True
