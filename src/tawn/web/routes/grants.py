"""Grants + audit routes — full-replacement editor.

Every PUT re-hashes in the same request so there is never a
tampered-looking intermediate state.
"""

from pathlib import Path

import yaml
from fastapi import APIRouter
from pydantic import BaseModel

from tawn.capability.audit import AuditLog
from tawn.capability.grants import load_verified
from tawn.capability.integrity import confirm as integrity_confirm
from tawn.home import tawn_home

router = APIRouter()


@router.get("/grants")
def get_grants():
    home = tawn_home()
    grants_path = home / "grants.yaml"
    if not grants_path.exists():
        return {"read": [], "write": [], "observe": [], "system": False, "mcp": []}
    g = load_verified(grants_path)
    return {
        "read": [str(p) for p in g.read],
        "write": [str(p) for p in g.write],
        "observe": g.observe,
        "system": g.system,
        "mcp": g.mcp,
    }


class GrantsBody(BaseModel):
    read: list[str] = []
    write: list[str] = []
    observe: list[str] = []
    system: bool = False
    mcp: list[str] = []


@router.put("/grants")
def put_grants(body: GrantsBody):
    home = tawn_home()
    home.mkdir(parents=True, exist_ok=True)
    path = home / "grants.yaml"
    data = {
        "read": [str(Path(p).expanduser().resolve()) for p in body.read],
        "write": [str(Path(p).expanduser().resolve()) for p in body.write],
        "observe": body.observe,
        "system": body.system,
        "mcp": body.mcp,
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    digest = integrity_confirm(path)
    AuditLog(home / "audit.log").record("grant.edit (web)", str(path), ok=True, detail=digest)
    return {"ok": True, "digest": digest}


@router.get("/audit")
def get_audit(limit: int = 100, offset: int = 0):
    home = tawn_home()
    log = AuditLog(home / "audit.log")
    all_e = log.entries()
    total = len(all_e)
    page = list(reversed(all_e))[offset : offset + limit]
    return {"total": total, "entries": page}


@router.get("/audit/export")
def export_audit(format: str = "json"):
    from fastapi.responses import PlainTextResponse

    home = tawn_home()
    log = AuditLog(home / "audit.log")
    if format == "csv":
        return PlainTextResponse(
            log.export_csv(),
            headers={"Content-Disposition": "attachment; filename=tawn-audit.csv"},
            media_type="text/csv",
        )
    return PlainTextResponse(
        log.export_json(),
        headers={"Content-Disposition": "attachment; filename=tawn-audit.json"},
        media_type="application/json",
    )


@router.get("/audit/verify")
def verify_audit():
    home = tawn_home()
    ok = AuditLog(home / "audit.log").verify_chain()
    return {"intact": ok}
