"""Ambient Observer — project-scoped work capture (design spec §6)."""

from tawn.observer.config import ObserverConfig, load_observer_config
from tawn.observer.projects import Project, discover_projects, tier_enabled

__all__ = [
    "ObserverConfig",
    "load_observer_config",
    "Project",
    "discover_projects",
    "tier_enabled",
]
