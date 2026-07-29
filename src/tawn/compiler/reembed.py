"""Re-embed chunks whose vectors came from a different embedder.

Switching embed models leaves every existing vector stale. A normal compile
will not fix this: it only reconsiders chunks whose *source files* changed, so
untouched files keep vectors from the old model forever. Recall filters to the
current model, so those chunks silently drop out of search — the corpus looks
intact while quietly shrinking.

`--rebuild` would fix it, but at the cost of re-reading and re-chunking
everything. This pass re-embeds in place: same chunks, new vectors.
"""

from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from tawn.compiler.embedder import EmbedError, embed_texts, get_embed_config
from tawn.memory.schema import Chunk

# Chunks per provider call, and rows between commits — progress must be
# durable during a run that can take hours.
GROUP = 32
COMMIT_EVERY = 200

# A multi-hour pass must survive a transient provider blip.
RETRIES = 3
BACKOFF_S = 2.0


def stale_count(session: Session, home: Path) -> int:
    """How many chunks carry a vector from something other than the current model."""
    model, _ = get_embed_config(home)
    if not model:
        return 0
    return session.query(Chunk).filter(_stale_filter(model)).count()


def _stale_filter(model: str):
    return or_(Chunk.embed_model != model, Chunk.embed_model.is_(None), Chunk.embedding.is_(None))


def reembed_stale(
    session: Session,
    home: Path,
    limit: int | None = None,
    progress=None,
) -> int:
    """Re-embed stale-model chunks in place. Returns how many were updated."""
    model, _ = get_embed_config(home)
    if not model:
        return 0

    q = session.query(Chunk).filter(_stale_filter(model)).order_by(Chunk.id)
    if limit:
        q = q.limit(limit)
    rows = q.all()
    if not rows:
        return 0

    done = 0
    for start in range(0, len(rows), GROUP):
        window = rows[start:start + GROUP]

        # Retry with backoff rather than abandoning the run. A single
        # transient blip — a rate limit, a dropped connection — would
        # otherwise end a multi-hour pass, and the next invocation would
        # start over from wherever it stopped. Only give up on a window
        # after the provider has failed repeatedly.
        vecs = used_model = dims = None
        for attempt in range(RETRIES):
            try:
                vecs, used_model, dims = embed_texts([c.content for c in window], home)
                break
            except EmbedError:
                if attempt < RETRIES - 1:
                    time.sleep(BACKOFF_S * (2 ** attempt))
        if vecs is None:
            # Stop cleanly, keeping everything already committed. Re-running
            # resumes from here — the query selects stale rows, not offsets.
            break
        for chunk, vec in zip(window, vecs):
            chunk.embedding = vec
            chunk.embed_model = used_model
            chunk.embed_dims = dims
        done += len(window)
        if done % COMMIT_EVERY < GROUP:
            session.commit()
        if progress:
            progress(done, len(rows))

    session.commit()
    return done
