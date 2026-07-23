"""brief() verb — domain summary from chunks + entities + wiki index."""

from __future__ import annotations

import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from tawn.home import tawn_home
from tawn.memory.schema import Chunk, Entity


def brief(
    domain: str,
    home: Path | None = None,
    session: Session | None = None,
) -> dict:
    """Return a summary brief for a domain.

    Keys: domain, summary, entity_count, chunk_count,
          last_compiled, staleness_hours, stale_chunk_count
    """
    home = home or tawn_home()

    chunk_count = 0
    stale_count = 0
    last_compiled: datetime.datetime | None = None
    entity_count = 0

    if session is not None:
        q = session.query(Chunk)
        if domain != "*":
            q = q.filter(Chunk.domain == domain)
        chunks = q.all()
        chunk_count = len(chunks)
        stale_count = sum(1 for c in chunks if c.stale)
        compiled_times = [c.compiled_at for c in chunks if c.compiled_at]
        if compiled_times:
            last_compiled = max(compiled_times)

        eq = session.query(Entity)
        if domain != "*":
            eq = eq.filter(Entity.domain == domain)
        entity_count = eq.count()

    # Read wiki summary from index.md
    summary = ""
    if domain != "*":
        wiki_index = home / "wiki" / domain / "index.md"
        if wiki_index.exists():
            text = wiki_index.read_text()
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith("_"):
                    summary = stripped
                    break

    staleness_hours: float | None = None
    if last_compiled:
        delta = datetime.datetime.utcnow() - last_compiled
        staleness_hours = round(delta.total_seconds() / 3600, 1)

    return {
        "domain": domain,
        "summary": summary,
        "entity_count": entity_count,
        "chunk_count": chunk_count,
        "last_compiled": last_compiled.isoformat() if last_compiled else None,
        "staleness_hours": staleness_hours,
        "stale_chunk_count": stale_count,
    }
