"""Projecting skills out to every agent on the machine.

Sync is one-way — Tawn writes, never deletes what it did not write. Each
directory Tawn creates gets a `.tawn-synced` marker, so a hand-written skill
that happens to share a name is reported as a conflict and left exactly as it
was. Silently overwriting someone's own work would be the worst possible
failure for a tool whose whole promise is "write it once, have it everywhere".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from tawn.skills.store import MARKER, SKILL_FILE, Skill, list_skills, slugify

#: agent → where it keeps skills. Each honours a `TAWN_SKILLS_DIR_<AGENT>`
#: override so tests cannot touch a developer's real ~/.claude.
SKILL_TARGETS: dict[str, str] = {
    "claude-code": "~/.claude/skills",
    "cursor": "~/.cursor/skills",
    "gemini-cli": "~/.gemini/skills",
    "codex": "~/.codex/skills",
}


@dataclass
class SyncReport:
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts


def _env_var(agent: str) -> str:
    return f"TAWN_SKILLS_DIR_{agent.upper().replace('-', '_')}"


def target_dir(agent: str) -> Path:
    override = os.environ.get(_env_var(agent))
    if override:
        return Path(override)
    return Path(SKILL_TARGETS[agent]).expanduser()


def detect_targets(require_existing: bool = True) -> list[tuple[str, Path]]:
    """Agents present on this machine.

    An agent counts as present when its skills directory exists *or* its
    parent config directory does — a fresh Claude Code install has the latter
    but not yet the former, and refusing to sync there would be unhelpful.
    """
    found: list[tuple[str, Path]] = []
    for agent in SKILL_TARGETS:
        d = target_dir(agent)
        if not require_existing or d.exists() or d.parent.exists():
            found.append((agent, d))
    return found


def _is_ours(d: Path) -> bool:
    return (d / MARKER).exists()


def sync_out(
    home: Path,
    grants=None,
    skills: list[Skill] | None = None,
    agents: list[str] | None = None,
) -> SyncReport:
    """Write every skill into each detected agent's skills directory.

    `grants` is accepted and checked when given: a target outside every
    `write:` grant is skipped rather than written to, because the capability
    layer is not something the skill system gets to bypass.
    """
    home = Path(home)
    report = SyncReport()
    to_write = skills if skills is not None else list_skills(home)
    if not to_write:
        return report

    targets = [
        (agent, d)
        for agent, d in detect_targets()
        if agents is None or agent in agents
    ]

    for agent, root in targets:
        if grants is not None and getattr(grants, "write", None) is not None:
            from tawn.capability.grants import path_allowed

            if not path_allowed(grants, root, "write"):
                report.skipped.append(f"{agent}: not under a `write:` grant")
                continue
        report.targets.append(agent)
        for skill in to_write:
            d = root / slugify(skill.name)
            f = d / SKILL_FILE
            if f.exists() and not _is_ours(d):
                report.conflicts.append(f"{agent}/{skill.name}")
                continue
            try:
                d.mkdir(parents=True, exist_ok=True)
                f.write_text(skill.to_markdown())
                (d / MARKER).write_text("written by tawn — safe to delete\n")
            except OSError as exc:
                report.skipped.append(f"{agent}/{skill.name}: {exc}")
                continue
            report.written.append(f"{agent}/{skill.name}")
    return report
