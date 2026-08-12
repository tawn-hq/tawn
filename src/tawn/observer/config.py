"""Observer tuning knobs, read from ~/.tawn/config.yaml under `observer:`."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

DEFAULT_AGENT_IDENTITIES = [
    "noreply@anthropic.com",
    "claude",
    "codex",
    "gemini",
    "bot@",
]


#: Local models able to follow "write these two sections and nothing else",
#: best first. Writing a review note is an instruction-following task, not a
#: knowledge one, so newer small models beat older larger ones — qwen3:0.6b is
#: ranked above tinyllama:1.1b despite having fewer parameters, because
#: tinyllama echoes its input back instead of answering.
REVIEW_MODEL_PREFERENCE = [
    "qwen2.5:7b",
    "llama3.1:8b",
    "qwen3:8b",
    "qwen3:4b",
    "gemma3:4b",
    "qwen2.5:3b",
    "qwen3:1.7b",
    "qwen3:0.6b",
]

#: Embedding models are installed alongside chat models and cannot answer a
#: prompt. Matched as substrings against the tag.
_EMBEDDING_MARKERS = ("embed", "minilm", "bge-", "e5-")


@dataclass(frozen=True)
class ObserverConfig:
    idle_minutes: int = 20
    correlation_window_seconds: int = 90
    burst_files: int = 4
    burst_window_ms: int = 3000
    burst_lines: int = 40
    burst_single_ms: int = 500
    #: Model used for review notes. Empty means "pick the best installed local
    #: model", so a fresh box works without configuration and a pulled upgrade
    #: takes effect without an edit.
    review_model: str = ""
    #: Where review notes are written. Empty means `~/.tawn/reviews/`. A path here
    #: must be write-granted — at that point it is one of the user's directories,
    #: not Tawn's own home.
    notes_dir: str = ""
    agent_identities: list[str] = field(
        default_factory=lambda: list(DEFAULT_AGENT_IDENTITIES)
    )


def is_chat_capable(tag: str) -> bool:
    """Whether a local tag can answer a prompt at all."""
    low = tag.lower()
    return not any(m in low for m in _EMBEDDING_MARKERS)


def pick_local_review_model(installed: list[str]) -> str | None:
    """Best installed model for writing a review note, or None if none fit.

    Preference order beats parameter count on purpose — see
    `REVIEW_MODEL_PREFERENCE`. An installed tag not on the list still wins over
    nothing, since an unknown model is more likely to follow instructions than a
    model already known to fail at it.
    """
    usable = [t for t in installed if is_chat_capable(t)]
    by_prefix = {t.split(":")[0]: t for t in reversed(usable)}
    for want in REVIEW_MODEL_PREFERENCE:
        if want in usable:
            return want
        # Tolerate a different tag of the same family, e.g. qwen3:0.6b-q4.
        base = want.split(":")[0]
        if base in by_prefix and want.split(":")[1] in by_prefix[base]:
            return by_prefix[base]
    unranked = [t for t in usable if "tinyllama" not in t.lower()]
    return unranked[0] if unranked else (usable[0] if usable else None)


def load_observer_config(home: Path) -> ObserverConfig:
    """Load the `observer:` block, falling back per-key to the defaults.

    Merging per-key rather than all-or-nothing means setting one knob does not
    silently reset the other six.
    """
    path = Path(home) / "config.yaml"
    if not path.exists():
        return ObserverConfig()
    try:
        raw = (yaml.safe_load(path.read_text()) or {}).get("observer") or {}
    except Exception:
        return ObserverConfig()
    known = {f.name for f in fields(ObserverConfig)}
    return ObserverConfig(**{k: v for k, v in raw.items() if k in known})
