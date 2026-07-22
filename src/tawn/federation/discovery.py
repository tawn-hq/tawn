"""Auto-detect known AI CLI tools and register them as federation sources."""

from __future__ import annotations

import shutil
from pathlib import Path

from tawn.federation.adapters.base import BaseAdapter
from tawn.federation.adapters.claude_code import ClaudeCodeAdapter
from tawn.federation.adapters.codex import CodexAdapter
from tawn.federation.config import FedSource, load_config, save_config

# Known adapter classes to auto-detect
_KNOWN: list[BaseAdapter] = [
    ClaudeCodeAdapter(),
    CodexAdapter(),
]

# Map adapter name → canonical watch path (first DETECT_PATHS entry)
_ADAPTER_DEFAULT_PATH: dict[str, str] = {
    a.name: a.DETECT_PATHS[0] for a in _KNOWN if a.DETECT_PATHS
}


def discover(
    home: Path,
    detect_paths_override: dict[str, str] | None = None,
) -> list[FedSource]:
    """Return FedSource entries for newly-detected tools not yet in config.

    detect_paths_override maps adapter-name → path string, for testing.
    """
    existing_names = {s.name for s in load_config(home)}
    path_map = detect_paths_override if detect_paths_override is not None else _ADAPTER_DEFAULT_PATH
    new_sources: list[FedSource] = []

    for adapter in _KNOWN:
        if adapter.name in existing_names:
            continue
        watch_path = path_map.get(adapter.name)
        if not watch_path:
            continue
        expanded = Path(watch_path).expanduser()
        if not expanded.exists():
            continue
        # Also check bin if specified (skip bin check when override provided)
        if adapter.DETECT_BINS and detect_paths_override is None:
            bin_name = adapter.DETECT_BINS[0]
            if shutil.which(bin_name) is None:
                continue
        new_sources.append(FedSource(
            name=adapter.name,
            path=watch_path,
            adapter=adapter.name.replace("-", "_"),
            format="auto",
            auto_detected=True,
        ))
    return new_sources


def run_discovery(
    home: Path,
    detect_paths_override: dict[str, str] | None = None,
) -> int:
    """Discover new tools, merge into config, return count of new sources added."""
    new_sources = discover(home, detect_paths_override)
    if not new_sources:
        return 0
    existing = load_config(home)
    save_config(home, existing + new_sources)
    return len(new_sources)
