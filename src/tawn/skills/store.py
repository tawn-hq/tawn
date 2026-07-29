"""Skill storage — `~/.tawn/skills/<name>/SKILL.md`.

The format is YAML frontmatter plus a markdown body, adopted from what Claude
Code already keeps in `~/.claude/skills/` rather than invented. That choice is
the whole point: a Tawn skill *is* a Claude Code skill, so syncing is a copy
and importing is a read, with no conversion step to drift out of date.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SKILLS_REL = "skills"
SKILL_FILE = "SKILL.md"
#: Written into every directory Tawn syncs a skill into, so a later sync knows
#: what it owns and never overwrites a hand-written file of the same name.
MARKER = ".tawn-synced"


@dataclass
class Skill:
    name: str
    description: str
    body: str = ""
    source: str = "authored"  # authored | imported
    imported_from: str | None = None
    path: Path | None = None
    extra: dict = field(default_factory=dict)

    def to_markdown(self) -> str:
        meta: dict = {"name": self.name, "description": self.description}
        if self.imported_from:
            meta["imported_from"] = self.imported_from
        meta.update(self.extra)
        front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
        return f"---\n{front}\n---\n\n{self.body.strip()}\n"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "untitled"


def content_hash(skill: Skill) -> str:
    """Identity for dedupe: the body, not the frontmatter.

    Provenance keys differ between a skill Tawn authored and the same skill
    read back after syncing, so hashing the whole file would make every
    round-trip look like a new skill.
    """
    return hashlib.sha256(skill.body.strip().encode("utf-8")).hexdigest()[:16]


_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)


def parse_skill(text: str, path: Path | None = None) -> Skill | None:
    """Read a SKILL.md. Returns None when it has no usable frontmatter."""
    m = _FRONTMATTER.match(text.lstrip("﻿"))
    if not m:
        return None
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except Exception:
        return None
    if not isinstance(meta, dict):
        return None

    name = str(meta.pop("name", "") or (path.parent.name if path else "")).strip()
    if not name:
        return None
    description = str(meta.pop("description", "") or "").strip()
    imported_from = meta.pop("imported_from", None)

    return Skill(
        name=name,
        description=description,
        body=m.group(2).strip(),
        source="imported" if imported_from else "authored",
        imported_from=imported_from,
        path=path,
        extra={k: v for k, v in meta.items()},
    )


def skills_root(home: Path) -> Path:
    return Path(home) / SKILLS_REL


def skill_dir(home: Path, name: str) -> Path:
    return skills_root(home) / slugify(name)


def list_skills(home: Path) -> list[Skill]:
    root = skills_root(Path(home))
    if not root.is_dir():
        return []
    out: list[Skill] = []
    for d in sorted(root.iterdir()):
        f = d / SKILL_FILE
        if not f.is_file():
            continue
        try:
            skill = parse_skill(f.read_text(errors="replace"), f)
        except OSError:
            continue
        if skill is not None:
            out.append(skill)
    return out


def get_skill(home: Path, name: str) -> Skill | None:
    f = skill_dir(Path(home), name) / SKILL_FILE
    if not f.is_file():
        return None
    try:
        return parse_skill(f.read_text(errors="replace"), f)
    except OSError:
        return None


def save_skill(home: Path, skill: Skill) -> Path:
    d = skill_dir(Path(home), skill.name)
    d.mkdir(parents=True, exist_ok=True)
    f = d / SKILL_FILE
    f.write_text(skill.to_markdown())
    skill.path = f
    return f


def remove_skill(home: Path, name: str) -> bool:
    import shutil

    d = skill_dir(Path(home), name)
    if not d.is_dir():
        return False
    shutil.rmtree(d)
    return True
