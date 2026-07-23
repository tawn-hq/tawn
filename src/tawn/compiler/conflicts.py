"""Conflict resolution across priority tiers.

When two chunks share the same content_hash, the higher-priority tier wins.
Lower tier number = higher priority (identity=1 beats agent-notes=3).
Conflicts are recorded to wiki/conflicts.md for human review.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from tawn.compiler.parser import ParsedChunk


def resolve_conflicts(
    chunks: list[ParsedChunk],
    wiki_dir: Path | None = None,
) -> list[ParsedChunk]:
    """Return deduplicated chunks; highest-priority tier wins per content_hash."""
    best: dict[str, ParsedChunk] = {}
    conflict_log: list[str] = []

    for chunk in chunks:
        h = chunk.content_hash
        if h not in best:
            best[h] = chunk
        else:
            existing = best[h]
            if chunk.priority_tier < existing.priority_tier:
                conflict_log.append(
                    f"- tier {existing.priority_tier} ({existing.source_path}) "
                    f"→ replaced by tier {chunk.priority_tier} ({chunk.source_path})"
                )
                best[h] = chunk
            else:
                conflict_log.append(
                    f"- tier {chunk.priority_tier} ({chunk.source_path}) "
                    f"→ kept tier {existing.priority_tier} ({existing.source_path})"
                )

    if conflict_log and wiki_dir is not None:
        wiki_dir.mkdir(parents=True, exist_ok=True)
        cfile = wiki_dir / "conflicts.md"
        existing_text = cfile.read_text() if cfile.exists() else ""
        header = f"\n## Conflict log — {datetime.datetime.utcnow().date()}\n\n"
        cfile.write_text(existing_text + header + "\n".join(conflict_log) + "\n")

    return list(best.values())
