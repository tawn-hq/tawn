"""Skill Factory — author once, project to every agent (design spec §8)."""

from tawn.skills.importer import ImportReport, discover_importable, import_skills
from tawn.skills.store import (
    Skill, content_hash, get_skill, list_skills, remove_skill, save_skill,
)
from tawn.skills.sync import SKILL_TARGETS, SyncReport, detect_targets, sync_out

__all__ = [
    "Skill", "content_hash", "get_skill", "list_skills", "remove_skill",
    "save_skill", "SKILL_TARGETS", "SyncReport", "detect_targets", "sync_out",
    "ImportReport", "discover_importable", "import_skills",
]
