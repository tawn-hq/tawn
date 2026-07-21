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
