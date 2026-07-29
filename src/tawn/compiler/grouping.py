"""Derive the card-grouping key for a chunk.

Three source shapes need three behaviours, and grouping purely by path gets
two of them wrong: a day of imported cloud memory lands in a single file
holding many unrelated conversations (one enormous card), while agent-memory
files are already one fact each (pointless one-item cards).

    history/*.jsonl              → one group per file
    granted repo documents       → one group per file
    raw/imports/<day>.md         → split on internal "# Chat Session:" seams
    .../memory/*.md              → ungrouped, single rows
"""

from __future__ import annotations

import re
from pathlib import Path

SESSION_SEAM_RE = re.compile(r"^#\s*Chat Session:\s*(.+)$", re.MULTILINE)


def _is_atomic_memory(source_path: str) -> bool:
    """Agent-memory files hold one fact each — grouping them adds nothing."""
    return "/memory/" in source_path.replace("\\", "/")


def _is_day_bucketed(source_path: str, home: Path) -> bool:
    """Imports land in one file per day, holding many unrelated conversations."""
    try:
        rel = Path(source_path).relative_to(Path(home) / "raw")
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0] == "imports"


def group_for(
    source_path: str,
    content: str,
    home: Path,
) -> tuple[str | None, str | None]:
    """Return (group_key, group_label). (None, None) means "do not group"."""
    if _is_atomic_memory(source_path):
        return None, None

    seam = SESSION_SEAM_RE.search(content)

    if _is_day_bucketed(source_path, home):
        if seam:
            title = seam.group(1).strip()
            return f"{source_path}#{title}", title
        return source_path, Path(source_path).stem

    if seam:
        return source_path, seam.group(1).strip()

    return source_path, Path(source_path).name
