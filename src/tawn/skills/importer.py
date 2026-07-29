"""Pulling in skills that already exist in other agents.

The dedupe rule is name **and** content hash. Tawn syncs skills out, so it will
later find its own writes sitting in `~/.claude/skills/` — importing those back
would fork every skill against itself on the second run. A skill directory
carrying the `.tawn-synced` marker is Tawn's own and is skipped outright; the
hash catches the rest.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from tawn.skills.store import (
    MARKER, SKILL_FILE, Skill, content_hash, get_skill, parse_skill,
    save_skill, slugify,
)
from tawn.skills.sync import SKILL_TARGETS, target_dir

#: Extra places skills hide, beyond each agent's main directory.
PLUGIN_GLOBS = [
    "~/.claude/plugins/cache/*/*/skills/*/SKILL.md",
    "~/.claude/plugins/*/skills/*/SKILL.md",
]


@dataclass
class ImportReport:
    imported: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    found: list[Skill] = field(default_factory=list)
    dry_run: bool = False


def _plugin_roots() -> list[Path]:
    override = os.environ.get("TAWN_SKILLS_PLUGIN_GLOB")
    if override:
        return [Path(p) for p in Path().glob(override)] if not Path(override).is_absolute() else _glob_absolute(override)
    out: list[Path] = []
    for pattern in PLUGIN_GLOBS:
        out.extend(_glob_absolute(pattern))
    return out


def _glob_absolute(pattern: str) -> list[Path]:
    expanded = os.path.expanduser(pattern)
    root = Path(expanded.split("*")[0]).parent
    rest = expanded[len(str(root)) :].lstrip("/")
    try:
        return sorted(root.glob(rest))
    except Exception:
        return []


def discover_importable() -> list[Skill]:
    """Every skill found in another agent, excluding Tawn's own syncs."""
    found: list[Skill] = []
    seen: set[tuple[str, str]] = set()

    sources: list[tuple[str, Path]] = []
    for agent in SKILL_TARGETS:
        root = target_dir(agent)
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if d.is_dir() and (d / SKILL_FILE).is_file():
                # Tawn wrote this one on a previous sync.
                if (d / MARKER).exists():
                    continue
                sources.append((agent, d / SKILL_FILE))

    for f in _plugin_roots():
        if f.is_file():
            sources.append(("claude-code-plugin", f))

    for agent, f in sources:
        try:
            skill = parse_skill(f.read_text(errors="replace"), f)
        except OSError:
            continue
        if skill is None:
            continue
        skill.source = "imported"
        skill.imported_from = agent
        key = (slugify(skill.name), content_hash(skill))
        if key in seen:
            continue
        seen.add(key)
        found.append(skill)
    return found


def import_skills(
    home: Path,
    skills: list[Skill] | None = None,
    dry_run: bool = False,
) -> ImportReport:
    """Import discovered skills into Tawn's own store."""
    home = Path(home)
    candidates = skills if skills is not None else discover_importable()
    report = ImportReport(found=candidates, dry_run=dry_run)

    for skill in candidates:
        existing = get_skill(home, skill.name)
        if existing is not None:
            if content_hash(existing) == content_hash(skill):
                # Same skill, already here — including one Tawn synced out and
                # is now meeting again.
                report.skipped.append(f"{skill.name} (already have it)")
            else:
                # Same name, different content. Never overwrite the user's own.
                report.conflicts.append(
                    f"{skill.name} (a different skill of this name already exists)"
                )
            continue
        if not dry_run:
            save_skill(home, skill)
        report.imported.append(skill.name)
    return report
