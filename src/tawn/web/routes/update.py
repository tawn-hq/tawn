"""HTTP routes for self-update and local model install."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["update"])


@router.get("/status")
def update_status():
    from tawn.updater import check_latest, get_status
    check_latest()
    return get_status()


@router.post("/trigger")
def trigger_update():
    from tawn.updater import trigger_update as _trigger
    return _trigger()


class OllamaPullBody(BaseModel):
    model: str


@router.post("/ollama-pull")
def ollama_pull(body: OllamaPullBody):
    import subprocess, shutil
    name = body.model.strip()
    if not name:
        return {"ok": False, "error": "model name required"}
    if not shutil.which("ollama"):
        return {"ok": False, "error": "ollama not found — install from ollama.com"}
    try:
        result = subprocess.run(
            ["ollama", "pull", name],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip() or "pull failed"}
        return {"ok": True, "model": name}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "pull timed out (10 min limit)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
