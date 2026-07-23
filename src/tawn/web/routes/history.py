"""Chat history routes — private, local-only sessions."""

from fastapi import APIRouter, HTTPException

from tawn.history import get_session, list_sessions
from tawn.home import tawn_home

router = APIRouter()


@router.get("/history")
def list_history():
    return list_sessions(tawn_home())


@router.get("/history/{session_id}")
def get_history_session(session_id: str):
    if ".." in session_id or "/" in session_id:
        raise HTTPException(status_code=400, detail="invalid session id")
    entries = get_session(tawn_home(), session_id)
    if entries is None:
        raise HTTPException(status_code=404)
    return entries
