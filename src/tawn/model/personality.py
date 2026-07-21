"""User personality profile — what Tawn knows about who it's talking to.

Stored at ~/.tawn/personality/profile.yaml. Injected into the identity
baseline so every model call is grounded in the user's context.
"""

from pathlib import Path

import yaml


def profile_path(home: Path) -> Path:
    return home / "personality" / "profile.yaml"


def load_profile(home: Path) -> dict:
    p = profile_path(home)
    if not p.exists():
        return {}
    try:
        data = yaml.safe_load(p.read_text()) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_profile(home: Path, profile: dict) -> None:
    p = profile_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True))


def profile_is_empty(home: Path) -> bool:
    p = load_profile(home)
    return not any(v for v in p.values() if v)


ONBOARDING_QUESTIONS = [
    ("name", "What's your name?"),
    ("role", "What do you do — your work or field in one line?"),
    ("focus", "What are you mainly using Tawn for right now?"),
]


def profile_summary(profile: dict) -> str:
    """One-paragraph summary of the profile for injection into the baseline."""
    if not profile:
        return ""
    parts = []
    if profile.get("name"):
        parts.append(f"The user's name is {profile['name']}.")
    if profile.get("role"):
        parts.append(f"They work as: {profile['role']}.")
    if profile.get("focus"):
        parts.append(f"Their current focus with Tawn: {profile['focus']}.")
    extra = {k: v for k, v in profile.items() if k not in ("name", "role", "focus") and v}
    for k, v in extra.items():
        parts.append(f"{k}: {v}.")
    return " ".join(parts)
