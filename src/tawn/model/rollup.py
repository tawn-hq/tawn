"""Fold ledger.jsonl into daily Postgres rollups.

The JSONL file is the source of truth; this table is a derived cache the UI
can query without parsing tens of thousands of lines. Recording every embed
call takes the ledger from dozens of entries to ~12,000 per rebuild, and
`Ledger.entries()` reads the whole file into memory.

A byte-offset watermark makes the pass incremental, and it advances only to
the last complete newline: an append interrupted mid-write leaves a partial
trailing line, and consuming it would record a truncated entry.

Because the table is derived, any disagreement with the file is resolved by
recomputing it — `reconcile(..., rebuild=True)` — rather than reconciling two
peers.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy.orm import Session

from tawn.memory.schema import LedgerWatermark, ModelCallRollup

LEDGER_NAME = "ledger.jsonl"


def _key(entry: dict) -> tuple:
    ts = entry.get("ts") or ""
    try:
        day = datetime.date.fromisoformat(ts[:10])
    except ValueError:
        day = datetime.date.today()
    return (
        day,
        entry.get("provider") or "unknown",
        entry.get("model") or "unknown",
        entry.get("caller") or "unknown",
        entry.get("operation") or "",
        entry.get("domain"),
    )


def _cost(entry: dict) -> tuple[Decimal, bool]:
    """(cost, priced) for one entry, repricing where the file could not.

    The ledger is append-only truth, so a line written when a model had no
    price recorded $0 forever — 1,306 real Gemini Pro calls read as free.
    But those lines carry their token counts, so the cost is recoverable now
    that the price is known. Rollups are a derived view, so recomputing here
    corrects the number without rewriting history.

    A recorded non-zero cost always wins: it is what the provider was
    actually charged against at the time.
    """
    from tawn.model.ledger import estimate_cost

    try:
        recorded = Decimal(str(entry.get("cost_usd") or "0"))
    except (InvalidOperation, ValueError):
        recorded = Decimal("0")

    if recorded > 0:
        return recorded, True

    model = entry.get("model") or ""
    recomputed, priced = estimate_cost(
        model,
        int(entry.get("tokens_in") or 0),
        int(entry.get("tokens_out") or 0),
    )
    if priced:
        return recomputed, True
    return recorded, _was_priced(entry)


def _was_priced(entry: dict) -> bool:
    """Whether this entry's cost is a real figure.

    Entries written before the `priced` flag existed have to be inferred, and
    the two obvious readings are both wrong: assuming priced hides 1,300 real
    Gemini Pro calls that billed as free, while assuming unpriced flags the
    entire historical ledger and tells the user nothing.

    So infer from what those entries do carry — a non-zero cost was computed
    from a real price, and a local model is genuinely free. Anything else
    charged something we could not price.
    """
    flag = entry.get("priced")
    if flag is not None:
        return bool(flag)

    from tawn.model.ledger import _is_local_model

    if (entry.get("locality") or "") == "local":
        return True
    if _is_local_model(entry.get("model") or ""):
        return True
    try:
        return Decimal(str(entry.get("cost_usd") or "0")) > 0
    except (InvalidOperation, ValueError):
        return False


def reconcile(home: Path, session: Session, rebuild: bool = False) -> dict:
    """Fold new ledger lines into rollups. Returns {entries, offset, rollups}."""
    path = Path(home) / LEDGER_NAME
    wm = session.get(LedgerWatermark, LEDGER_NAME)

    if rebuild:
        session.query(ModelCallRollup).delete()
        if wm is not None:
            wm.byte_offset = 0
            wm.entries_seen = 0
        session.flush()

    if not path.exists():
        return {"entries": 0, "offset": 0, "rollups": 0}

    start = 0 if (rebuild or wm is None) else (wm.byte_offset or 0)
    size = path.stat().st_size
    # Rotated or truncated: the stored offset points past the end, so the file
    # is not the one we were reading. Start over rather than skip silently.
    if start > size:
        start = 0

    with path.open("rb") as fh:
        fh.seek(start)
        blob = fh.read()

    # Consume only up to the final newline. Anything after it is a partial
    # write the producer has not finished, and parsing it would either throw
    # or record a truncated entry.
    cut = blob.rfind(b"\n")
    if cut == -1:
        return {"entries": 0, "offset": start, "rollups": 0}
    consumed = blob[: cut + 1]
    new_offset = start + len(consumed)

    buckets: dict[tuple, dict] = {}
    count = 0
    for line in consumed.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue

        count += 1
        acc = buckets.setdefault(_key(entry), {
            "calls": 0, "tokens_in": 0, "tokens_out": 0,
            "cost": Decimal("0"), "unpriced": 0,
        })
        acc["calls"] += 1
        acc["tokens_in"] += int(entry.get("tokens_in") or 0)
        acc["tokens_out"] += int(entry.get("tokens_out") or 0)
        cost, priced = _cost(entry)
        acc["cost"] += cost
        if not priced:
            acc["unpriced"] += 1

    for key, acc in buckets.items():
        day, provider, model, caller, operation, domain = key
        row = (
            session.query(ModelCallRollup)
            .filter_by(day=day, provider=provider, model=model,
                       caller=caller, operation=operation, domain=domain)
            .first()
        )
        if row is None:
            row = ModelCallRollup(
                day=day, provider=provider, model=model, caller=caller,
                operation=operation, domain=domain,
                calls=0, tokens_in=0, tokens_out=0,
                cost_usd=Decimal("0"), unpriced_calls=0,
            )
            session.add(row)
        row.calls += acc["calls"]
        row.tokens_in += acc["tokens_in"]
        row.tokens_out += acc["tokens_out"]
        row.cost_usd = (row.cost_usd or Decimal("0")) + acc["cost"]
        row.unpriced_calls += acc["unpriced"]

    if wm is None:
        wm = LedgerWatermark(path=LEDGER_NAME, byte_offset=0, entries_seen=0)
        session.add(wm)
    wm.byte_offset = new_offset
    wm.entries_seen = (wm.entries_seen or 0) + count
    wm.updated_at = datetime.datetime.utcnow()
    session.commit()

    return {"entries": count, "offset": new_offset, "rollups": len(buckets)}
