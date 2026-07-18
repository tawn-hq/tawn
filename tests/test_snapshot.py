from decimal import Decimal

from tawn.capability.audit import AuditLog
from tawn.domains.wealth.holdings import Holdings
from tawn.domains.wealth.snapshot import (
    compute_state,
    latest_snapshot,
    snapshot_history,
    take_snapshot,
)

HOLDINGS = Holdings.model_validate(
    {
        "fx_usdngn": 1000,  # easy math
        "targets": {"ngx": 30, "us": 10, "usd": 30, "land": 20, "cash": 10},
        "ngx": [{"ticker": "GTCO", "units": 100, "price": "50"}],  # 5_000
        "us": [{"ticker": "AAPL", "units": 1, "price": "5"}],      # 5 USD → 5_000
        "usd": [{"name": "savings", "value_usd": 10}],             # 10_000
        "land": [{"name": "plot", "value_ngn": 3000}],             # 3_000
        "cash": [{"name": "bank", "value_ngn": 2000}],             # 2_000
    }
)  # total: 25_000 NGN
PRICES = {"GTCO": Decimal("50")}
US_PRICES = {"AAPL": Decimal("5")}


def test_compute_state_totals_and_percentages():
    state = compute_state(HOLDINGS, PRICES, US_PRICES, "manual")
    assert state["total_ngn"] == "25000"
    assert state["classes"]["ngx"]["value_ngn"] == "5000"
    assert state["classes"]["ngx"]["pct"] == "20"
    assert state["classes"]["us"]["value_ngn"] == "5000"
    assert state["classes"]["usd"]["pct"] == "40"
    assert state["price_source"] == "manual"
    markets = {p["market"] for p in state["positions"]}
    assert markets == {"ngx", "us"}


def test_take_snapshot_persists_and_audits(db_engine, tmp_path):
    audit = AuditLog(tmp_path / "audit.log")
    take_snapshot(db_engine, HOLDINGS, PRICES, US_PRICES, "manual", audit)
    latest = latest_snapshot(db_engine)
    assert latest is not None and latest["total_ngn"] == "25000"
    assert any(e["op"] == "wealth.snapshot" and e["ok"] for e in audit.entries())


def test_history_orders_by_time(db_engine, tmp_path):
    from datetime import datetime, timedelta, timezone

    audit = AuditLog(tmp_path / "audit.log")
    t0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(3):
        take_snapshot(
            db_engine, HOLDINGS, PRICES, US_PRICES, "manual", audit,
            asof=t0 + timedelta(days=i),
        )
    hist = snapshot_history(db_engine)
    assert len(hist) == 3
    assert hist[0][0] < hist[-1][0]
    assert hist[0][1] == Decimal("25000")
