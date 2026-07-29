"""Backfill chunk grouping for rows compiled before grouping existed.

The feed groups chunks into one card per source document or conversation,
reading `chunk_groups`. Two ways that table ends up unable to feed the view:

  * chunks written before grouping shipped carry no `group_key` at all, and a
    normal compile will not fix them — it only reprocesses files whose
    *contents* changed, so untouched sources keep their old rows forever;
  * `chunk_groups` can be emptied (a purge, a killed rebuild) while the chunks
    themselves survive.

Either leaves the feed blank while the corpus is intact. Grouping is derivable
from `source_path` and content, so this repairs both in place — no re-parsing,
no re-embedding, no model calls.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from tawn.compiler.classifier import classify
from tawn.compiler.grouping import group_for
from tawn.memory.schema import Chunk, ChunkGroup

COMMIT_EVERY = 500


def ungrouped_count(session: Session) -> int:
    """Chunks with no group_key — invisible to the grouped feed."""
    return session.query(Chunk).filter(Chunk.group_key.is_(None)).count()


def backfill_groups(session: Session, home: Path, progress=None) -> int:
    """Derive missing group keys, then rebuild `chunk_groups`. Returns rows touched."""
    rows = session.query(Chunk).filter(Chunk.group_key.is_(None)).all()

    touched = 0
    for i, chunk in enumerate(rows):
        gkey, glabel = group_for(chunk.source_path, chunk.content or "", home)
        chunk.group_key = gkey
        chunk.group_label = glabel
        touched += 1
        if (i + 1) % COMMIT_EVERY == 0:
            session.commit()
            if progress:
                progress(i + 1, len(rows))
    session.commit()

    # Rebuild the aggregate for every group present, including groups whose
    # chunks already had keys but whose rows were purged.
    agg = (
        session.query(
            Chunk.group_key,
            func.count(Chunk.id),
            func.min(Chunk.group_label),
        )
        .filter(Chunk.group_key.isnot(None))
        .group_by(Chunk.group_key)
        .all()
    )

    for gkey, count, label in agg:
        domain_rows = (
            session.query(Chunk.domain, func.count(Chunk.id))
            .filter(Chunk.group_key == gkey)
            .group_by(Chunk.domain)
            .all()
        )
        dominant = max(domain_rows, key=lambda r: r[1])[0] if domain_rows else None

        grp = session.get(ChunkGroup, gkey)
        if grp is None:
            session.add(ChunkGroup(
                group_key=gkey, title=label, domain=dominant, chunk_count=count,
            ))
        else:
            grp.chunk_count = count
            grp.domain = dominant
            if not grp.title:
                grp.title = label
    session.commit()
    return touched


def backfill_domains(session: Session, home: Path, progress=None) -> int:
    """Classify chunks stored with no domain. Returns how many were assigned.

    `parse_file` used to drop the caller's inferred domain for markdown, so
    every classified external `.md` was stored with domain NULL and vanished
    from per-domain views. That is fixed at the source, but a normal compile
    will not revisit files whose contents have not changed — so existing rows
    need repairing in place.

    Classifies against the file on disk when it is still there, falling back
    to the stored chunk text: granted sources move and get deleted, and the
    text we kept is classifiable on its own. A `None` verdict is left as NULL
    rather than forced into a bucket — not everything belongs to a life-area.
    """
    rows = session.query(Chunk).filter(Chunk.domain.is_(None)).all()

    assigned = 0
    for i, chunk in enumerate(rows):
        path = Path(chunk.source_path)
        content = ""
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8", errors="replace")[:2000]
            except OSError:
                content = ""
        if not content:
            content = (chunk.content or "")[:2000]

        verdict = classify(path, content)
        if verdict:
            chunk.domain = verdict
            assigned += 1

        if (i + 1) % COMMIT_EVERY == 0:
            session.commit()
            if progress:
                progress(i + 1, len(rows))

    session.commit()
    return assigned
