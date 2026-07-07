"""Tawn home directory: TAWN_HOME resolution and skeleton creation.

Spec: design spec §3.2 canonical store; §14 stage 0.
"""

import os
from pathlib import Path

#: Directories of the canonical store (design spec §3.2 + later stages' homes).
SKELETON = [
    "raw/agent-notes",
    "wiki",
    "vectors",
    "domains",
    "federation/inbox",
    "federation/adapters",
    "failures",
    "handoffs",
    "personality",
]


def tawn_home() -> Path:
    """The Tawn home; TAWN_HOME env overrides ~/.tawn (tests rely on this)."""
    return Path(os.environ.get("TAWN_HOME", "~/.tawn")).expanduser().resolve()


def init_home(home: Path) -> list[Path]:
    """Create the skeleton idempotently. Returns newly created dirs only."""
    created: list[Path] = []
    for rel in SKELETON:
        d = home / rel
        if not d.is_dir():
            d.mkdir(parents=True)
            created.append(d)
    return created
