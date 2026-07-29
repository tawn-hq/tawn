"""Grants + audit routes — full-replacement editor.

Every PUT re-hashes in the same request so there is never a
tampered-looking intermediate state.
"""

from pathlib import Path

import yaml
from fastapi import APIRouter
from pydantic import BaseModel

from fastapi import HTTPException

from tawn.capability.audit import AuditLog, audit_path
from tawn.capability.grants import load_verified
from tawn.capability.integrity import IntegrityError
from tawn.home import tawn_home

router = APIRouter()


@router.get("/grants")
def get_grants():
    home = tawn_home()
    grants_path = home / "grants.yaml"
    if not grants_path.exists():
        return {"read": [], "write": [], "observe": [], "system": False, "mcp": []}
    try:
        g = load_verified(grants_path)
    except IntegrityError as exc:
        # grants.yaml was written by something that skipped the confirm
        # step (a hand edit, or a bug in another writer) — surface it as a
        # clean, actionable error instead of an unhandled 500.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "read": [str(p) for p in g.read],
        "write": [str(p) for p in g.write],
        "observe": g.observe,
        "system": g.system,
        "mcp": g.mcp,
    }


@router.post("/grants/confirm")
def confirm_grants():
    """Refused: confirming must happen on the machine that owns the grants.

    This endpoint used to confirm the integrity sidecar over HTTP. Paired with
    `PUT /api/grants` it handed a caller both halves of the control — write any
    grants, then bless them — so the tamper-evidence proved nothing. Since the
    web surface has no authentication, "a caller" means anyone who can reach
    the port.

    Kept rather than deleted so the UI gets an explanation instead of a 404.
    """
    return {
        "ok": False,
        "error": (
            "Confirming grants over HTTP is disabled. Run `tawn grant confirm` "
            "on this machine — the integrity check only means something if the "
            "acknowledgement comes from somewhere the network cannot reach."
        ),
    }


class GrantsBody(BaseModel):
    read: list[str] = []
    write: list[str] = []
    observe: list[str] = []
    mcp: list[str] = []
    # `net` and `shell` were missing here after Stage 10 added them, so saving
    # from Settings silently erased whatever the user had set by hand.
    net: bool = False
    shell: bool = False
    # `system` is deliberately absent. It is the full-machine-awareness flag,
    # and the web surface has no authentication — it must not be reachable
    # here. Whatever is on disk is preserved untouched.


@router.put("/grants")
def put_grants(body: GrantsBody):
    """Write grants, leaving them *unconfirmed*.

    This used to call `integrity_confirm` on its own write. The sidecar exists
    to make an edit Tawn did not perform detectable, so a handler that confirms
    itself defeats the control entirely — the change looked authentic no matter
    who made it. Now the file is written and the integrity record is left
    stale, so the edit must be acknowledged from the machine itself with
    `tawn grant confirm`. Until then nothing loads the new grants.

    `system` is never written from here; whatever is on disk survives.
    """
    home = tawn_home()
    home.mkdir(parents=True, exist_ok=True)
    path = home / "grants.yaml"

    existing: dict = {}
    if path.exists():
        try:
            existing = yaml.safe_load(path.read_text()) or {}
        except Exception:
            existing = {}

    data = {
        "read": [str(Path(p).expanduser().resolve()) for p in body.read],
        "write": [str(Path(p).expanduser().resolve()) for p in body.write],
        "observe": body.observe,
        # Preserved, never set from the web.
        "system": bool(existing.get("system", False)),
        "mcp": body.mcp,
        "net": body.net,
        "shell": body.shell,
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    AuditLog(audit_path(home)).record(
        "grant.edit (web, unconfirmed)", str(path), ok=True,
        detail="awaiting `tawn grant confirm`", actor="web",
    )
    return {
        "ok": True,
        "confirmed": False,
        "message": (
            "Grants written but not yet active. Run `tawn grant confirm` on "
            "this machine to acknowledge the change."
        ),
    }


@router.get("/audit")
def get_audit(limit: int = 100, offset: int = 0):
    home = tawn_home()
    log = AuditLog(audit_path(home))
    all_e = log.entries()
    total = len(all_e)
    page = list(reversed(all_e))[offset : offset + limit]
    return {"total": total, "entries": page}


@router.get("/audit/export")
def export_audit(format: str = "json"):
    from fastapi.responses import PlainTextResponse

    home = tawn_home()
    log = AuditLog(audit_path(home))
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
    # Returns the structured result directly. Previously this assigned
    # verify_chain() to `ok` and wrapped it — once that became a dict, the
    # truthiness check would have reported every chain intact, including
    # broken ones.
    return AuditLog(audit_path(tawn_home())).verify_chain()
