"""recall() verb — semantic search over compiled chunks."""

from __future__ import annotations

import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from tawn.compiler.embedder import EmbedError, embed_text, get_embed_config
from tawn.home import tawn_home
from tawn.memory.schema import Chunk


def _cosine_search(
    session: Session,
    vec: list[float],
    domain: str | None,
    top_k: int,
    asof: datetime.datetime | None,
) -> list[Chunk]:
    """Cosine similarity search; falls back to all chunks on SQLite."""
    import os
    db_url = os.environ.get("TAWN_DB_URL", "")
    query = session.query(Chunk).filter(Chunk.stale.is_(False))
    if domain:
        query = query.filter(Chunk.domain == domain)
    if asof:
        query = query.filter(Chunk.compiled_at <= asof)

    if "postgresql" in db_url and vec:
        try:
            query = query.order_by(Chunk.embedding.cosine_distance(vec))  # type: ignore[attr-defined]
            return query.limit(top_k).all()
        except Exception:
            pass

    return query.limit(top_k).all()


def _like_search(
    session: Session,
    query_str: str,
    domain: str | None,
    top_k: int,
    asof: datetime.datetime | None,
) -> list[Chunk]:
    from sqlalchemy import or_
    q = session.query(Chunk).filter(Chunk.stale.is_(False))
    if domain:
        q = q.filter(Chunk.domain == domain)
    if asof:
        q = q.filter(Chunk.compiled_at <= asof)
    keywords = [w.strip() for w in query_str.split() if len(w.strip()) > 2]
    if keywords:
        q = q.filter(or_(*[Chunk.content.ilike(f"%{kw}%") for kw in keywords]))
    return q.order_by(Chunk.priority_tier, Chunk.asof.desc()).limit(top_k).all()


def recall(
    query: str,
    domain: str | None = None,
    top_k: int = 5,
    format: str = "snippets",
    sensitive: bool = False,
    asof: datetime.datetime | None = None,
    home: Path | None = None,
    session: Session | None = None,
    router=None,
) -> dict:
    """Semantic search over compiled chunks.

    Returns SnippetResult dict when format='snippets',
    ComposedResult dict when format='composed'.
    On EmbedError falls back to full-text and includes 'embed_error' key.
    """
    home = home or tawn_home()
    embed_model, _ = get_embed_config(home)

    if session is None:
        from tawn.db import make_engine
        with Session(make_engine()) as s:
            return recall(
                query=query, domain=domain, top_k=top_k, format=format,
                sensitive=sensitive, asof=asof, home=home, session=s, router=router,
            )

    embed_error: str | None = None
    try:
        vec = embed_text(query, home)
        chunks = _cosine_search(session, vec, domain, top_k, asof)
    except EmbedError as e:
        embed_error = str(e)
        chunks = _like_search(session, query, domain, top_k, asof)

    chunk_dicts = [
        {
            "content": c.content,
            "source": c.source_path,
            "domain": c.domain,
            "score": None,
            "asof": c.asof.isoformat() if c.asof else None,
            "stale": c.stale,
        }
        for c in chunks
    ]

    if format == "composed":
        fallback_answer = "\n\n".join(
            f"[{c['source']}]\n{c['content'][:400]}" for c in chunk_dicts
        ) or ""
        if router is not None and chunks:
            context = "\n\n".join(f"[{c.source_path}]\n{c.content}" for c in chunks)
            from tawn.model.types import Message
            prompt = (
                f"Answer the following question using only the context provided.\n\n"
                f"Question: {query}\n\n"
                f"Context:\n{context}\n\nAnswer concisely."
            )
            answer = ""
            tokens_in = tokens_out = 0
            try:
                for chunk in router.stream([Message(role="user", content=prompt)], sensitive=sensitive):
                    answer += chunk.text
                    if chunk.done:
                        tokens_in = chunk.tokens_in or 0
                        tokens_out = chunk.tokens_out or 0
            except Exception:
                answer = fallback_answer
        else:
            answer = fallback_answer
            tokens_in = tokens_out = 0
        result: dict = {
            "format": "composed",
            "query": query,
            "answer": answer,
            "sources": list({c.source_path for c in chunks}),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
        if embed_error:
            result["embed_error"] = embed_error
        return result

    result = {
        "format": "snippets",
        "query": query,
        "chunks": chunk_dicts,
        "entity_hits": [],
        "searched_domains": [domain] if domain else [],
        "embed_model": embed_model or "unknown",
    }
    if embed_error:
        result["embed_error"] = embed_error
    return result
