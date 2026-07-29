"""Observable projects, derived from the `read:` grants.

Deriving projects from `read:` rather than a second list means the Observer can
never reach a path Tawn was not already permitted to index, and there is no way
for two grant lists to drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tawn.capability.grants import Grants

TIERS = ("fs", "git", "agents")


@dataclass(frozen=True)
class Project:
    root: Path
    name: str
    is_git: bool


def tier_enabled(grants: Grants, tier: str) -> bool:
    """True when this attribution tier is switched on in `observe:`."""
    return tier in (grants.observe or [])


def discover_projects(grants: Grants) -> list[Project]:
    roots = [Path(r) for r in (grants.read or []) if Path(r).is_dir()]
    counts: dict[str, int] = {}
    for r in roots:
        counts[r.name] = counts.get(r.name, 0) + 1
    out: list[Project] = []
    for r in roots:
        # Two granted paths can share a leaf name (code/tawn, archive/tawn).
        # A project name is a user-facing key and a directory name in the
        # review tree, so a collision must not silently merge two projects.
        name = r.name if counts[r.name] == 1 else f"{r.parent.name}/{r.name}"
        out.append(Project(root=r, name=name, is_git=(r / ".git").exists()))
    return out
