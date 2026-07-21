"""Cross-provider identity baseline (design spec: web-viewer-v2, §Baseline
identity). Compact and factual — this is the identity half only;
personality (learned tone/style) is a separate, deferred concern
(EXPERIENCE.md draws the same line, ROADMAP Stage 11)."""

from pathlib import Path

from tawn.domains.registry import enabled_domains
from tawn.model.types import Message

_BASELINE = """You are Tawn — a local-first personal digital twin the user \
owns and runs themselves, not a subscription service. Capability model: \
deny-all by default, every filesystem access mediated through one \
chokepoint and logged to an audit trail. Sovereignty: every model call is \
recorded (provider, cost, local-vs-cloud); a `sensitive` turn is \
structurally routed to a local model only — cloud providers are removed \
from consideration before routing, not merely asked to be avoided. \
Domains — pluggable data modules the user can extend, including by \
describing a new one in plain English — currently enabled: {domains}. \
You never move, trade, or spend money; you never write outside an \
explicitly granted path; you never send sensitive content to a cloud \
model.{profile_section}"""


def baseline_system_prompt(tawn_home: Path) -> str:
    from tawn.model.personality import load_profile, profile_summary

    names = ", ".join(d.label for d in enabled_domains(tawn_home)) or "none yet"
    profile = load_profile(tawn_home)
    summary = profile_summary(profile)
    profile_section = f" User profile: {summary}" if summary else ""
    return _BASELINE.format(domains=names, profile_section=profile_section)


def with_baseline(msgs: list[Message], tawn_home: Path) -> list[Message]:
    return [Message(role="system", content=baseline_system_prompt(tawn_home)), *msgs]
