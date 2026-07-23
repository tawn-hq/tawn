"""User-editable Tawn configuration stored at ~/.tawn/config.yaml.

Separate from TawnSettings (env/DSN) — this is for user preferences
that should be editable from the CLI and persisted across sessions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_DEFAULTS: dict[str, Any] = {
    "theme": "system",              # system | dark | light
    "model": "auto",                # provider/model slug or "auto"
    "web_port": 8787,
    "compile_interval_minutes": 5,
    "federation_merge_interval_minutes": 5,
    "memory_max_mb": None,          # None = no limit; integer → systemd MemoryMax
    "cpu_weight": 50,               # systemd CPUWeight (1-10000); 50 = half default
    "db_pool_size": 2,              # SQLAlchemy pool_size for the web server
    "lazy_compile": True,           # only compile when sentinel present
}

_VALID: dict[str, tuple] = {
    "theme": ("system", "dark", "light"),
    "model": None,                  # any string
    "web_port": None,               # any int 1024-65535
    "compile_interval_minutes": None,
    "federation_merge_interval_minutes": None,
    "memory_max_mb": None,          # int or null
    "cpu_weight": None,             # int 1-10000
    "db_pool_size": None,
    "lazy_compile": None,
}

_CONFIG_FILE = "config.yaml"


def _config_path(home: Path) -> Path:
    return home / _CONFIG_FILE


def load_user_config(home: Path) -> dict[str, Any]:
    """Load config.yaml; fill missing keys with defaults."""
    p = _config_path(home)
    data: dict[str, Any] = {}
    if p.exists():
        try:
            loaded = yaml.safe_load(p.read_text()) or {}
            if isinstance(loaded, dict):
                data = loaded
        except yaml.YAMLError:
            pass
    merged = dict(_DEFAULTS)
    merged.update({k: v for k, v in data.items() if k in _DEFAULTS})
    return merged


def save_user_config(home: Path, cfg: dict[str, Any]) -> None:
    """Persist config dict to config.yaml (chmod 600)."""
    p = _config_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump(cfg, default_flow_style=False, sort_keys=True))
    p.chmod(0o600)


def get_config_value(home: Path, key: str) -> Any:
    """Get one config key. Raises KeyError if unknown."""
    if key not in _DEFAULTS:
        raise KeyError(f"unknown config key: {key!r}")
    return load_user_config(home).get(key, _DEFAULTS[key])


def set_config_value(home: Path, key: str, raw_value: str) -> Any:
    """Parse raw_value string and persist. Returns the coerced value."""
    if key not in _DEFAULTS:
        raise KeyError(f"unknown config key: {key!r}")

    # Validate enum keys
    allowed = _VALID.get(key)
    if allowed is not None and raw_value not in allowed:
        raise ValueError(f"{key} must be one of {allowed}")

    # Coerce types
    default = _DEFAULTS[key]
    if isinstance(default, bool):
        coerced: Any = raw_value.lower() in ("true", "1", "yes", "on")
    elif isinstance(default, int):
        coerced = int(raw_value)
    elif default is None and raw_value.lower() in ("null", "none", ""):
        coerced = None
    elif default is None:
        # Try int first, then string
        try:
            coerced = int(raw_value)
        except ValueError:
            coerced = raw_value
    else:
        coerced = raw_value

    cfg = load_user_config(home)
    cfg[key] = coerced
    save_user_config(home, cfg)
    return coerced


def reset_config_value(home: Path, key: str) -> Any:
    """Reset one key to its default."""
    if key not in _DEFAULTS:
        raise KeyError(f"unknown config key: {key!r}")
    cfg = load_user_config(home)
    cfg[key] = _DEFAULTS[key]
    save_user_config(home, cfg)
    return _DEFAULTS[key]


def all_keys() -> list[str]:
    return list(_DEFAULTS.keys())


def defaults() -> dict[str, Any]:
    return dict(_DEFAULTS)
