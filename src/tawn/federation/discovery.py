"""Auto-detect known AI CLI tools and register them as federation sources."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from tawn.federation.adapters.base import BaseAdapter
from tawn.federation.adapters.claude_code import ClaudeCodeAdapter
from tawn.federation.adapters.codex import CodexAdapter
from tawn.federation.adapters.gemini_cli import GeminiCliAdapter
from tawn.federation.config import FedSource, load_config, save_config

# Known adapter classes to auto-detect
_KNOWN: list[BaseAdapter] = [
    ClaudeCodeAdapter(),
    CodexAdapter(),
    GeminiCliAdapter(),
]

# Map adapter name → canonical watch path (first DETECT_PATHS entry)
_ADAPTER_DEFAULT_PATH: dict[str, str] = {
    a.name: a.DETECT_PATHS[0] for a in _KNOWN if a.DETECT_PATHS
}


_SCAN_LIMIT = 500  # bound the walk — these dirs can hold thousands of files


def _any_matching_file(adapter: BaseAdapter, root: Path) -> bool:
    """True if root contains at least one file this adapter can actually parse."""
    if root.is_file():
        try:
            return adapter.can_handle(root)
        except Exception:
            return False
    try:
        for i, f in enumerate(root.rglob("*")):
            if i >= _SCAN_LIMIT:
                break
            if not f.is_file():
                continue
            try:
                if adapter.can_handle(f):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _env_override_var(adapter_name: str) -> str:
    return f"TAWN_DETECT_PATH_{adapter_name.upper().replace('-', '_')}"


def discover(
    home: Path,
    detect_paths_override: dict[str, str] | None = None,
) -> list[FedSource]:
    """Return FedSource entries for newly-detected tools not yet in config.

    detect_paths_override maps adapter-name → path string, for testing.
    Without an override, each adapter's real-world path can still be
    swapped via TAWN_DETECT_PATH_<NAME> (e.g. TAWN_DETECT_PATH_CODEX) —
    the same isolation knob tests use so a real ~/.codex or ~/.gemini on
    the machine running the suite can't leak into an "empty" test.
    claude-code additionally honors TAWN_AGENT_MEMORY_DIR, since that env
    var already governs its path everywhere else in the compiler.
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
        if detect_paths_override is not None:
            expanded = Path(watch_path).expanduser()
        elif adapter.name == "claude-code":
            from tawn.home import agent_memory_root
            expanded = agent_memory_root()
        else:
            env_path = os.environ.get(_env_override_var(adapter.name))
            expanded = Path(env_path).expanduser() if env_path else Path(watch_path).expanduser()
        if not expanded.exists():
            continue
        # A real, adapter-parseable file under the path is stronger evidence
        # of "this tool has been used" than the CLI binary being on $PATH
        # right now — e.g. Codex used only via its VS Code extension leaves
        # real session data with no standalone `codex` binary ever installed.
        # Bin-on-PATH is only a fallback signal when scanning finds nothing.
        has_real_data = _any_matching_file(adapter, expanded)
        if not has_real_data and adapter.DETECT_BINS and detect_paths_override is None:
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
