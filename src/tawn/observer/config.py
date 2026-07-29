"""Observer tuning knobs, read from ~/.tawn/config.yaml under `observer:`."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

DEFAULT_AGENT_IDENTITIES = [
    "noreply@anthropic.com",
    "claude",
    "codex",
    "gemini",
    "bot@",
]


@dataclass(frozen=True)
class ObserverConfig:
    idle_minutes: int = 20
    correlation_window_seconds: int = 90
    burst_files: int = 4
    burst_window_ms: int = 3000
    burst_lines: int = 40
    burst_single_ms: int = 500
    agent_identities: list[str] = field(
        default_factory=lambda: list(DEFAULT_AGENT_IDENTITIES)
    )


def load_observer_config(home: Path) -> ObserverConfig:
    """Load the `observer:` block, falling back per-key to the defaults.

    Merging per-key rather than all-or-nothing means setting one knob does not
    silently reset the other six.
    """
    path = Path(home) / "config.yaml"
    if not path.exists():
        return ObserverConfig()
    try:
        raw = (yaml.safe_load(path.read_text()) or {}).get("observer") or {}
    except Exception:
        return ObserverConfig()
    known = {f.name for f in fields(ObserverConfig)}
    return ObserverConfig(**{k: v for k, v in raw.items() if k in known})
