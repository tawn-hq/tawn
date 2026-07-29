"""Cached tool discovery.

Listing a stdio server's tools spawns its process, so the result is cached with
a TTL — the same shape `model/discovery.py` uses for model lists. The cache
reports its own provenance (live / cache / stale) so the UI can say which it is
showing rather than presenting a day-old list as current.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from tawn.mcp.client import probe
from tawn.mcp.registry import MCPServer

CACHE_TTL_SECONDS = 24 * 60 * 60
_REL = "mcp/catalog.json"


def _path(home: Path) -> Path:
    return Path(home) / _REL


def _load_cache(home: Path) -> dict:
    path = _path(home)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_cache(home: Path, cache: dict) -> None:
    path = _path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2))


def get_tools(
    home: Path,
    server: MCPServer,
    refresh: bool = False,
    now: float | None = None,
) -> tuple[list[dict], str]:
    """Return (tools, source) where source is `live`, `cache` or `stale`.

    `now` is injectable so TTL behaviour is testable without sleeping.
    """
    now = time.time() if now is None else now
    cache = _load_cache(home)
    entry = cache.get(server.name)

    if not refresh and entry and (now - entry.get("fetched_at", 0)) < CACHE_TTL_SECONDS:
        return entry.get("tools", []), "cache"

    health = probe(server)
    if health.reachable:
        cache[server.name] = {"fetched_at": now, "tools": health.tools}
        _save_cache(home, cache)
        return health.tools, "live"

    # Unreachable. A stale list beats no list, but it must announce itself.
    if entry:
        return entry.get("tools", []), "stale"
    return [], "stale"


def cached_tools(home: Path, server_name: str) -> list[dict]:
    """Whatever is cached for this server, without connecting."""
    return (_load_cache(home).get(server_name) or {}).get("tools", [])


def forget(home: Path, server_name: str) -> None:
    cache = _load_cache(home)
    if cache.pop(server_name, None) is not None:
        _save_cache(home, cache)
