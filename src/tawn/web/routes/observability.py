"""Audit events and model spend — one surface.

"What has my twin been doing, and what did it cost" is one question asked two
ways, so the event stream and the cost rollups are served together.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from tawn.capability.audit import AuditLog, audit_path
from tawn.db import get_session
from tawn.home import tawn_home
from tawn.memory.schema import LedgerWatermark, ModelCallRollup

router = APIRouter(tags=["observability"])


def _log() -> AuditLog:
    return AuditLog(audit_path(tawn_home()))


def _usd(x) -> str:
    """Serialize money as a string, never a float.

    `ModelCallRollup.cost_usd` is `Numeric(18, 8)` and its own column comment says
    why: "money summed through binary floating point drifts, and a cost dashboard
    that disagrees with its own source is worse than none." This route was
    converting to float and then summing — precisely the drift the column exists
    to prevent, on the same spend-reporting path where reconciliation once found
    $12.21 of real spend recorded as $0.0021.

    Trailing zeros are trimmed so 8 decimal places of storage do not become 8
    decimal places of display.
    """
    d = Decimal(x or 0).quantize(Decimal("0.00000001"))
    return f"{d:f}".rstrip("0").rstrip(".") or "0"


@router.get("/events")
def get_events(
    actor: str | None = None,
    op: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """Audit entries, newest first."""
    entries = _log().entries()
    if actor:
        entries = [e for e in entries if e.get("actor") == actor]
    if op:
        entries = [e for e in entries if op in (e.get("op") or "")]
    total = len(entries)
    page = list(reversed(entries))[offset: offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "entries": page}


@router.get("/verify")
def get_verify():
    """Chain integrity, including where a break is if there is one."""
    return _log().verify_chain()


@router.get("/spend")
def get_spend(session: Session = Depends(get_session)):
    """Model spend, grouped every way worth asking about."""
    rows = session.query(ModelCallRollup).all()

    def _group(attr: str) -> list[dict]:
        acc: dict = {}
        for r in rows:
            key = getattr(r, attr) or "unknown"
            bucket = acc.setdefault(
                key, {"calls": 0, "cost_usd": Decimal(0), "unpriced": 0}
            )
            bucket["calls"] += r.calls
            bucket["cost_usd"] += Decimal(r.cost_usd or 0)
            bucket["unpriced"] += r.unpriced_calls
        return [
            {attr: k, **{**v, "cost_usd": _usd(v["cost_usd"])}}
            for k, v in sorted(acc.items(), key=lambda kv: -kv[1]["calls"])
        ]

    return {
        "total_calls": sum(r.calls for r in rows),
        "total_cost_usd": _usd(sum((Decimal(r.cost_usd or 0) for r in rows), Decimal(0))),
        # Reported alongside the total so the figure can state its own
        # incompleteness rather than quietly understating spend.
        "unpriced_calls": sum(r.unpriced_calls for r in rows),
        "total_tokens_in": sum(r.tokens_in for r in rows),
        "total_tokens_out": sum(r.tokens_out for r in rows),
        "by_operation": _group("operation"),
        "by_provider": _group("provider"),
        "by_caller": _group("caller"),
        "by_day": [
            {"day": str(d), "calls": c, "cost_usd": _usd(cost)}
            for d, c, cost in session.query(
                ModelCallRollup.day,
                func.sum(ModelCallRollup.calls),
                func.sum(ModelCallRollup.cost_usd),
            ).group_by(ModelCallRollup.day).order_by(ModelCallRollup.day).all()
        ],
    }


@router.get("/spend/status")
def get_spend_status(session: Session = Depends(get_session)):
    """How current the rollups are.

    Surfaced so the page can show stale totals that admit staleness, rather
    than wrong totals that do not.
    """
    from tawn.model.rollup import LEDGER_NAME

    wm = session.get(LedgerWatermark, LEDGER_NAME)
    ledger = Path(tawn_home()) / LEDGER_NAME
    size = ledger.stat().st_size if ledger.exists() else 0
    offset = (wm.byte_offset if wm else 0) or 0
    return {
        "last_reconciled": wm.updated_at.isoformat() if wm and wm.updated_at else None,
        "entries_seen": (wm.entries_seen if wm else 0) or 0,
        "pending_bytes": max(0, size - offset),
    }


@router.post("/reconcile")
def post_reconcile(rebuild: bool = False, session: Session = Depends(get_session)):
    from tawn.model.rollup import reconcile

    return reconcile(tawn_home(), session, rebuild=rebuild)
