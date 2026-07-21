"""Domain plugin contract (design spec: domain-plugin-architecture).

DomainSpec is the one shape every domain — built-in or third-party —
registers as. mediated_fs() is shared infrastructure any domain module
can use for its own capability-gated file I/O, same pattern wealth
already used from cli.py.
"""

from dataclasses import dataclass
from pathlib import Path

import typer
from fastapi import APIRouter

from tawn.capability.audit import AuditLog
from tawn.capability.fs import MediatedFS
from tawn.capability.grants import load_verified
from tawn.home import tawn_home


@dataclass
class DomainSpec:
    name: str
    label: str
    cli: typer.Typer | None = None
    api_router: APIRouter | None = None
    nav: bool = True


def mediated_fs(home: Path | None = None) -> MediatedFS:
    home = home or tawn_home()
    grants = load_verified(home / "grants.yaml")
    return MediatedFS(grants, AuditLog(home / "audit.log"), home=home)
