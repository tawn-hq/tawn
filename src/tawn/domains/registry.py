"""Domain discovery + enable/disable trust gate (design spec:
domain-plugin-architecture). A discovered domain — entry_points or a
local folder under ~/.tawn/domains/ — is not active until enabled;
mirrors the grants deny-all pattern.
"""
import importlib.metadata
import importlib.util
from pathlib import Path

import yaml

from tawn.capability.audit import AuditLog
from tawn.domains.base import DomainSpec
from tawn.home import tawn_home

ENTRY_POINT_GROUP = "tawn.domains"


def _domains_yaml_path(home: Path) -> Path:
    return home / "domains.yaml"


def enabled_names(home: Path) -> set[str]:
    path = _domains_yaml_path(home)
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text()) or {}
    return set(data.get("enabled", []))


def _write_enabled(home: Path, names: set[str]) -> None:
    path = _domains_yaml_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"enabled": sorted(names)}, sort_keys=True))


def enable(name: str, home: Path | None = None) -> None:
    home = home or tawn_home()
    names = enabled_names(home)
    names.add(name)
    _write_enabled(home, names)
    AuditLog(home / "audit.log").record("domain.enable", name, ok=True)


def disable(name: str, home: Path | None = None) -> None:
    home = home or tawn_home()
    names = enabled_names(home)
    names.discard(name)
    _write_enabled(home, names)
    AuditLog(home / "audit.log").record("domain.disable", name, ok=True)


def discovered_entry_point_domains() -> dict[str, str]:
    """{name: source dist name} for every entry_points-registered domain."""
    out: dict[str, str] = {}
    for ep in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
        out[ep.name] = ep.dist.name if ep.dist else "unknown"
    return out


def _load_entry_point(name: str) -> DomainSpec | None:
    for ep in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
        if ep.name == name:
            register = ep.load()
            return register()
    return None


def _local_domain_dirs(home: Path) -> list[Path]:
    root = home / "domains"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "domain.py").exists())


def _load_local_domain(folder: Path) -> DomainSpec | None:
    spec = importlib.util.spec_from_file_location(
        f"tawn_local_domain_{folder.name}", folder / "domain.py"
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module.register()
    except Exception:
        return None  # broken local domain — skip, don't crash the CLI/web


def enabled_domains(home: Path | None = None) -> list[DomainSpec]:
    home = home or tawn_home()
    names = enabled_names(home)
    specs: list[DomainSpec] = []
    for name in discovered_entry_point_domains():
        if name in names:
            spec = _load_entry_point(name)
            if spec is not None:
                specs.append(spec)
    for folder in _local_domain_dirs(home):
        if folder.name in names:
            spec = _load_local_domain(folder)
            if spec is not None:
                specs.append(spec)
    return specs


def discovered_all(home: Path | None = None) -> list[dict]:
    """For `tawn domain list` — every discoverable domain, enabled or not."""
    home = home or tawn_home()
    names = enabled_names(home)
    out = []
    for name, source in discovered_entry_point_domains().items():
        out.append({"name": name, "source": source, "enabled": name in names})
    for folder in _local_domain_dirs(home):
        out.append({"name": folder.name, "source": "local", "enabled": folder.name in names})
    return out
