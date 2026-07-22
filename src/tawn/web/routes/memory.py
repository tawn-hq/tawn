"""HTTP routes for memory verbs: recall / note / brief / compile."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from tawn.compiler.compiler import compile_status, run_compile
from tawn.db import get_session
from tawn.home import tawn_home
from tawn.memory.brief import brief as brief_verb
from tawn.memory.note import note as note_verb
from tawn.memory.recall import recall as recall_verb

router = APIRouter(tags=["memory"])


class NoteRequest(BaseModel):
    payload: str = Field(..., min_length=1)
    domain: str | None = None
    type: str = "observation"
    confidence: str = "medium"
    source: str | None = None
    ttl_days: int | None = None


class RecallRequest(BaseModel):
    query: str
    domain: str | None = None
    top_k: int = 5
    format: Literal["snippets", "composed"] = "snippets"
    sensitive: bool = False


@router.post("/note")
def post_note(body: NoteRequest):
    return note_verb(
        payload=body.payload,
        domain=body.domain,
        type=body.type,
        confidence=body.confidence,
        source=body.source,
        ttl_days=body.ttl_days,
        home=tawn_home(),
    )


@router.post("/recall")
def post_recall(body: RecallRequest, session: Session = Depends(get_session)):
    return recall_verb(
        query=body.query,
        domain=body.domain,
        top_k=body.top_k,
        format=body.format,
        sensitive=body.sensitive,
        home=tawn_home(),
        session=session,
    )


@router.get("/brief/{domain}")
def get_brief(domain: str, session: Session = Depends(get_session)):
    return brief_verb(domain=domain, home=tawn_home(), session=session)


@router.get("/compile/status")
def get_compile_status(session: Session = Depends(get_session)):
    return compile_status(tawn_home(), session=session)


@router.post("/compile")
def post_compile(session: Session = Depends(get_session)):
    result = run_compile(home=tawn_home(), session=session)
    return {
        "ok": result.ok,
        "files_processed": result.files_processed,
        "chunks_added": result.chunks_added,
        "chunks_removed": result.chunks_removed,
        "entities_resolved": result.entities_resolved,
        "error": result.error,
    }


@router.get("/chunks")
def list_chunks(
    domain: str | None = None,
    source_type: str | None = None,
    limit: int = 40,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    """Browse compiled chunks — newest first. Use for the memory feed."""
    from tawn.memory.schema import Chunk as _Chunk
    import os as _os
    q = session.query(_Chunk)
    if domain:
        q = q.filter(_Chunk.domain == domain)
    total = q.count()
    rows = q.order_by(_Chunk.compiled_at.desc()).offset(offset).limit(limit).all()
    home = tawn_home()
    hist_str = str(home / "history")
    raw_str = str(home / "raw")
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "chunks": [
            {
                "id": r.id,
                "domain": r.domain,
                "source_path": r.source_path,
                "source_label": _source_label(r.source_path, hist_str, raw_str),
                "source_type": "history" if r.source_path.startswith(hist_str) else
                               "raw" if r.source_path.startswith(raw_str) else "external",
                "content": r.content,
                "content_hash": r.content_hash,
                "priority_tier": r.priority_tier,
                "stale": r.stale,
                "compiled_at": r.compiled_at.isoformat() if r.compiled_at else None,
                "asof": r.asof.isoformat() if r.asof else None,
            }
            for r in rows
        ],
    }


def _source_label(source_path: str, hist_str: str, raw_str: str) -> str:
    if source_path.startswith(hist_str):
        from pathlib import Path as _Path
        return "chat: " + _Path(source_path).stem[:12]
    if source_path.startswith(raw_str):
        from pathlib import Path as _Path
        p = _Path(source_path)
        parts = p.parts
        raw_idx = next((i for i, x in enumerate(parts) if x == "raw"), None)
        return "/".join(parts[raw_idx + 1:]) if raw_idx is not None else p.name
    from pathlib import Path as _Path
    return _Path(source_path).name


@router.get("/chunks/{chunk_id}")
def get_chunk(chunk_id: int, session: Session = Depends(get_session)):
    from tawn.memory.schema import Chunk as _Chunk
    from fastapi import HTTPException
    row = session.get(_Chunk, chunk_id)
    if not row:
        raise HTTPException(status_code=404, detail="chunk not found")
    home = tawn_home()
    hist_str = str(home / "history")
    raw_str = str(home / "raw")
    return {
        "id": row.id,
        "domain": row.domain,
        "source_path": row.source_path,
        "source_label": _source_label(row.source_path, hist_str, raw_str),
        "source_type": "history" if row.source_path.startswith(hist_str) else
                       "raw" if row.source_path.startswith(raw_str) else "external",
        "content": row.content,
        "content_hash": row.content_hash,
        "priority_tier": row.priority_tier,
        "stale": row.stale,
        "compiled_at": row.compiled_at.isoformat() if row.compiled_at else None,
        "asof": row.asof.isoformat() if row.asof else None,
        "chunk_index": row.chunk_index,
    }
