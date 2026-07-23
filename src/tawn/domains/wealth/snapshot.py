"""Wealth snapshots: value the holdings, persist the state (spec §5
snapshots table). Read-only over the world; writes only its own rows."""

import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.engine import Engine

from tawn.capability.audit import AuditLog
from tawn.db import Snapshot, session
from tawn.domains.wealth.holdings import Holdings


def _dec(x: Decimal) -> str:
    # plain decimal string, never scientific notation (normalize() gives 2E+4)
    s = f"{x.quantize(Decimal('0.01')):f}".rstrip("0").rstrip(".")
    return s or "0"


def compute_state(
    holdings: Holdings,
    ngx_prices: dict[str, Decimal],
    us_prices: dict[str, Decimal],
    price_source: str,
) -> dict:
    positions = []

    def _value_equities(items, prices: dict[str, Decimal], market: str, to_ngn: Decimal) -> Decimal:
        total = Decimal(0)
        for p in items:
            price = prices.get(p.ticker)
            value = (price * p.units * to_ngn) if price is not None else Decimal(0)
            total += value
            positions.append(
                {
                    "market": market,
                    "ticker": p.ticker,
                    "units": str(p.units),
                    "price": str(price) if price is not None else None,
                    "value_ngn": _dec(value),
                }
            )
        return total

    ngx_total = _value_equities(holdings.ngx, ngx_prices, "ngx", Decimal(1))
    us_total = _value_equities(holdings.us, us_prices, "us", holdings.fx_usdngn)
    usd_total = sum(
        ((p.value_usd or Decimal(0)) * holdings.fx_usdngn for p in holdings.usd),
        Decimal(0),
    )
    land_total = sum((p.value_ngn or Decimal(0) for p in holdings.land), Decimal(0))
    cash_total = sum((p.value_ngn or Decimal(0) for p in holdings.cash), Decimal(0))
    classes = {
        "ngx": ngx_total,
        "us": us_total,
        "usd": usd_total,
        "land": land_total,
        "cash": cash_total,
    }
    total = sum(classes.values(), Decimal(0))
    return {
        "total_ngn": _dec(total),
        "classes": {
            name: {
                "value_ngn": _dec(value),
                "pct": _dec(value / total * 100 if total else Decimal(0)),
            }
            for name, value in classes.items()
        },
        "positions": positions,
        "price_source": price_source,
    }


def take_snapshot(
    engine: Engine,
    holdings: Holdings,
    ngx_prices: dict[str, Decimal],
    us_prices: dict[str, Decimal],
    price_source: str,
    audit: AuditLog,
    asof: datetime | None = None,
) -> dict:
    state = compute_state(holdings, ngx_prices, us_prices, price_source)
    asof = asof or datetime.now(timezone.utc)
    with session(engine) as s:
        s.add(Snapshot(domain="wealth", asof=asof, state_json=json.dumps(state)))
        s.commit()
    # Always runs via `tawn wealth snapshot` — invoked directly or by the
    # systemd timer running that same CLI command — so "cli" is accurate
    # either way; there's no separate non-CLI code path into this function.
    audit.record("wealth.snapshot", "snapshots", ok=True, detail=f"total={state['total_ngn']}", actor="cli")
    return state


def latest_snapshot(engine: Engine) -> dict | None:
    with session(engine) as s:
        row = s.scalars(
            select(Snapshot)
            .where(Snapshot.domain == "wealth")
            .order_by(Snapshot.asof.desc())
        ).first()
        return json.loads(row.state_json) if row else None


def snapshot_history(engine: Engine, limit: int = 30) -> list[tuple[datetime, Decimal]]:
    with session(engine) as s:
        rows = s.scalars(
            select(Snapshot)
            .where(Snapshot.domain == "wealth")
            .order_by(Snapshot.asof.desc())
            .limit(limit)
        ).all()
    return [
        (r.asof, Decimal(json.loads(r.state_json)["total_ngn"])) for r in reversed(rows)
    ]
