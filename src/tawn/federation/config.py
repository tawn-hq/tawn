"""Read/write federation/adapters/config.yaml — the list of watched sources."""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml


@dataclass
class FedSource:
    name: str
    path: str                  # raw string; expanduser at watch time
    adapter: str               # adapter name key
    format: str = "auto"       # auto | jsonl | markdown
    added: str = field(default_factory=lambda: datetime.date.today().isoformat())
    auto_detected: bool = False


_CONFIG_REL = "federation/adapters/config.yaml"


def _config_path(home: Path) -> Path:
    return home / _CONFIG_REL


def load_config(home: Path) -> list[FedSource]:
    path = _config_path(home)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    return [FedSource(**s) for s in data.get("sources", [])]


def save_config(home: Path, sources: list[FedSource]) -> None:
    path = _config_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"sources": [asdict(s) for s in sources]}
    path.write_text(yaml.dump(payload, default_flow_style=False, sort_keys=False))
