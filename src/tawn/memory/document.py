"""Reassemble a group's chunks into one readable document.

Chunking exists for retrieval: ~3,200-character slices are the right size to
embed and to match a query against. They are the wrong size to *read* — a card
listing five arbitrary fragments of one file asks the reader to reassemble the
document in their head, and the split points fall mid-sentence because they
were chosen by length, not meaning.

So the two jobs are separated. `recall` keeps working on chunks, which is
correct for search. Reading works on the document this rebuilds from them, in
order. Nothing is re-parsed and no model is called: the chunks already hold
the text, cleaned, and their order is recorded.

Rebuilt from chunks rather than re-read from `source_path` on purpose — the
original file may have moved or been deleted, and what Tawn actually knows is
what it stored.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from tawn.memory.schema import Chunk, ChunkGroup


def reconstruct(session: Session, group_key: str) -> dict | None:
    """Return one document for `group_key`, or None if the group has no chunks."""
    chunks = (
        session.query(Chunk)
        .filter(Chunk.group_key == group_key)
        .order_by(Chunk.source_path, Chunk.chunk_index)
        .all()
    )
    if not chunks:
        return None

    group = session.get(ChunkGroup, group_key)

    # Chunks are contiguous slices, so joining in order restores the prose.
    # A blank line between them keeps markdown block structure intact — the
    # splitter cut on heading and size boundaries, not mid-block.
    body = "\n\n".join((c.content or "").strip() for c in chunks if (c.content or "").strip())

    source_paths: list[str] = []
    for c in chunks:
        if c.source_path not in source_paths:
            source_paths.append(c.source_path)

    domains = [c.domain for c in chunks if c.domain]
    dominant = max(set(domains), key=domains.count) if domains else None

    title = (group.title if group else None) or Path(source_paths[0]).name

    return {
        "group_key": group_key,
        "title": title,
        "summary": group.summary if group else None,
        "domain": dominant,
        "body": body,
        "chunk_count": len(chunks),
        # How much of this document has a generated summary yet — lets the
        # reader tell "no summary" from "summary still pending".
        "enriched_chunks": sum(1 for c in chunks if c.enriched_at is not None),
        "source_paths": source_paths,
        "chunk_ids": [c.id for c in chunks],
        "stale": any(c.stale for c in chunks),
    }
