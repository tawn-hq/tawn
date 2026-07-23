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
    source_type: str | None = None,   # "knowledge" (default) | "imports" | "all"
    limit: int = 40,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    """Browse compiled chunks — newest first. Use for the memory feed.

    source_type:
      knowledge (default) — agent-memory + raw notes, no session imports
      imports             — session import files only
      all                 — everything
    """
    from tawn.home import agent_memory_root
    from tawn.memory.schema import Chunk as _Chunk
    home = tawn_home()
    hist_str = str(home / "history")
    raw_str = str(home / "raw")
    imports_str = str(home / "raw" / "imports")
    agent_mem_str = str(agent_memory_root())

    q = session.query(_Chunk)
    if domain:
        q = q.filter(_Chunk.domain == domain)

    src = source_type or "knowledge"
    if src == "knowledge":
        q = q.filter(~_Chunk.source_path.like(imports_str + "/%"))
    elif src == "imports":
        q = q.filter(_Chunk.source_path.like(imports_str + "/%"))
    # "all" → no additional filter

    total = q.count()
    rows = q.order_by(_Chunk.compiled_at.desc()).offset(offset).limit(limit).all()

    def _stype(path: str) -> str:
        if path.startswith(agent_mem_str) and "/memory/" in path:
            return "agent-memory"
        if path.startswith(imports_str):
            return "imports"
        if path.startswith(hist_str):
            return "history"
        if path.startswith(raw_str):
            return "raw"
        return "external"

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "source_type": src,
        "chunks": [
            {
                "id": r.id,
                "domain": r.domain,
                "source_path": r.source_path,
                "source_label": _source_label(r.source_path, hist_str, raw_str, agent_mem_str),
                "source_type": _stype(r.source_path),
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


def _source_label(source_path: str, hist_str: str, raw_str: str, agent_mem_str: str = "") -> str:
    from pathlib import Path as _Path
    if agent_mem_str and source_path.startswith(agent_mem_str) and "/memory/" in source_path:
        p = _Path(source_path)
        # Encoded dir: -home-testys-Documents-GitHub-certin → "certin"
        encoded = p.parent.parent.name  # e.g. -home-testys-Documents-GitHub-certin
        proj = encoded.rsplit("-", 1)[-1]  # last dash-segment is project name
        return f"{proj}/{p.stem}"
    if source_path.startswith(hist_str):
        return "chat: " + _Path(source_path).stem[:12]
    if source_path.startswith(raw_str):
        p = _Path(source_path)
        parts = p.parts
        raw_idx = next((i for i, x in enumerate(parts) if x == "raw"), None)
        return "/".join(parts[raw_idx + 1:]) if raw_idx is not None else p.name
    return _Path(source_path).name


@router.get("/chunks/stats")
def get_chunk_stats(session: Session = Depends(get_session)):
    """Return chunk counts by source type for the database management view."""
    from tawn.home import agent_memory_root
    from tawn.memory.schema import Chunk as _Chunk
    home = tawn_home()
    imports_str = str(home / "raw" / "imports")
    hist_str = str(home / "history")
    raw_str = str(home / "raw")
    agent_mem_str = str(agent_memory_root())

    total = session.query(_Chunk).count()
    imports_count = session.query(_Chunk).filter(_Chunk.source_path.like(imports_str + "/%")).count()
    agent_mem_count = session.query(_Chunk).filter(
        _Chunk.source_path.like(agent_mem_str + "/%")
    ).count()
    history_count = session.query(_Chunk).filter(_Chunk.source_path.like(hist_str + "/%")).count()
    raw_count = (
        session.query(_Chunk)
        .filter(_Chunk.source_path.like(raw_str + "/%"))
        .filter(~_Chunk.source_path.like(imports_str + "/%"))
        .count()
    )
    with_embed = session.query(_Chunk).filter(_Chunk.embedding.isnot(None)).count()
    from tawn.compiler.embedder import get_embed_config
    embed_model, embed_dims = get_embed_config(home)
    return {
        "total": total,
        "with_embeddings": with_embed,
        "embed_model": embed_model or None,
        "embed_dims": embed_dims or None,
        "by_type": {
            "agent-memory": agent_mem_count,
            "imports": imports_count,
            "history": history_count,
            "raw": raw_count,
        },
    }


@router.delete("/chunks")
def delete_chunks(
    source_type: str = "imports",   # "imports" | "history" | "all"
    session: Session = Depends(get_session),
):
    """Purge chunks by source type. Deletes FileState entries too so next compile re-indexes."""
    from pathlib import Path as _Path
    from tawn.memory.schema import Chunk as _Chunk, FileState as _FileState
    home = tawn_home()
    imports_str = str(home / "raw" / "imports")
    hist_str = str(home / "history")

    if source_type == "imports":
        paths = [r[0] for r in session.query(_Chunk.source_path).filter(
            _Chunk.source_path.like(imports_str + "/%")
        ).distinct().all()]
        deleted = session.query(_Chunk).filter(_Chunk.source_path.like(imports_str + "/%")).delete(synchronize_session=False)
        session.query(_FileState).filter(_FileState.path.like(imports_str + "/%")).delete(synchronize_session=False)
    elif source_type == "history":
        paths = [r[0] for r in session.query(_Chunk.source_path).filter(
            _Chunk.source_path.like(hist_str + "/%")
        ).distinct().all()]
        deleted = session.query(_Chunk).filter(_Chunk.source_path.like(hist_str + "/%")).delete(synchronize_session=False)
        session.query(_FileState).filter(_FileState.path.like(hist_str + "/%")).delete(synchronize_session=False)
    elif source_type == "all":
        deleted = session.query(_Chunk).delete(synchronize_session=False)
        session.query(_FileState).delete(synchronize_session=False)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="source_type must be imports|history|all")

    session.commit()
    return {"ok": True, "deleted": deleted}


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
