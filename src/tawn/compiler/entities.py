"""Entity extraction + fuzzy resolution.

Extracts candidates from chunk frontmatter (entity: field) and capitalised
noun phrases, fuzzy-matches against the entities table, and resolves or
queues ambiguous cases to review-queue.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from tawn.compiler.parser import ParsedChunk
from tawn.memory.schema import Entity

_EXACT_THRESHOLD = 95      # fuzz.ratio >= this → treat as same entity
_AMBIGUOUS_LOW = 80        # fuzz.ratio in [80, 95) with 2+ candidates → review queue


def _extract_candidates(chunk: ParsedChunk) -> list[str]:
    """Entity candidates declared in frontmatter.

    Free-text extraction moved to `compiler.enrich`, which asks a model rather
    than harvesting Title-cased word pairs. The old regex took any two
    consecutive capitalised words from raw content — including code and stack
    traces — and produced 8,524 rows of mostly noise: `OK Traceback`,
    `None File`, `TypeError Object`, `Also I'm`.
    """
    candidates: list[str] = []
    val = chunk.frontmatter.get("entity")
    if isinstance(val, list):
        candidates.extend(str(v).strip() for v in val if v)
    elif val:
        candidates.append(str(val).strip())

    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for c in candidates:
        if c not in seen and len(c) > 1:
            seen.add(c)
            result.append(c)
    return result


def _find_matches(
    candidate: str,
    all_entities: list[Entity],
) -> tuple[list[Entity], list[Entity]]:
    """Return (exact_matches, close_but_ambiguous) for a candidate name."""
    exact: list[Entity] = []
    close: list[Entity] = []
    candidate_lower = candidate.lower()
    for entity in all_entities:
        score = fuzz.ratio(candidate_lower, entity.canonical.lower())
        if score >= _EXACT_THRESHOLD:
            exact.append(entity)
        elif score >= _AMBIGUOUS_LOW:
            close.append(entity)
    return exact, close


def _write_review(candidate: str, matches: list[Entity], review_dir: Path) -> None:
    review_dir.mkdir(parents=True, exist_ok=True)
    rfile = review_dir / "entity-conflicts.md"
    existing = rfile.read_text() if rfile.exists() else ""
    match_list = ", ".join(e.canonical for e in matches)
    entry = (
        f"\n## Ambiguous: {candidate!r}\n"
        f"Close matches: {match_list}\n"
        f"Detected: {datetime.datetime.utcnow().isoformat()}\n"
        "Resolution: (review manually)\n"
    )
    rfile.write_text(existing + entry)


def extract_and_resolve(
    chunks: list[ParsedChunk],
    session: Session,
    review_dir: Path,
) -> int:
    """Extract entities from chunks, resolve against DB, return resolved count."""
    all_entities = session.query(Entity).all()
    resolved = 0

    for chunk in chunks:
        candidates = _extract_candidates(chunk)
        domain = chunk.frontmatter.get("domain")

        for candidate in candidates:
            exact, close = _find_matches(candidate, all_entities)

            if exact:
                for e in exact:
                    e.last_updated = datetime.datetime.utcnow()
                resolved += 1
            elif len(close) > 1:
                _write_review(candidate, close, review_dir)
            elif len(close) == 1:
                close[0].last_updated = datetime.datetime.utcnow()
                resolved += 1
            else:
                new_entity = Entity(
                    canonical=candidate,
                    domain=domain,
                    source_path=chunk.source_path,
                )
                session.add(new_entity)
                all_entities.append(new_entity)
                resolved += 1

    return resolved
