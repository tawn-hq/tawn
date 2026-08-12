import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tawn.memory.schema import ModelCallRollup
from tawn.web import create_app


def _client_for(db_engine):
    """Bind the app to the test engine.

    `Depends(get_session)` builds its own engine from settings, so without
    the override every request would hit the developer's real Postgres.
    """
    import tawn.db as db_mod

    def _get_session():
        with Session(db_engine) as s:
            yield s

    app = create_app(db_engine)
    app.dependency_overrides[db_mod.get_session] = _get_session
    return TestClient(app)


@pytest.fixture()
def client(tawn_home, db_engine):
    tawn_home.mkdir(parents=True, exist_ok=True)
    return _client_for(db_engine)


def _rollup(**kw):
    base = dict(
        day=datetime.date(2026, 7, 26), provider="gemini",
        model="gemini-2.5-flash", caller="cli", operation="embed",
        domain=None, calls=5, tokens_in=500, tokens_out=0,
        cost_usd=Decimal("0.001"), unpriced_calls=2,
    )
    base.update(kw)
    return ModelCallRollup(**base)


def test_events_returns_audit_entries(client, tawn_home):
    from tawn.capability.audit import AuditLog, audit_path

    AuditLog(audit_path(tawn_home)).record("init", "/x", ok=True, actor="cli")
    body = client.get("/api/observability/events").json()
    assert body["total"] == 1
    assert body["entries"][0]["op"] == "init"


def test_events_filter_by_actor(client, tawn_home):
    from tawn.capability.audit import AuditLog, audit_path

    log = AuditLog(audit_path(tawn_home))
    log.record("a", "/x", ok=True, actor="cli")
    log.record("b", "/y", ok=True, actor="web")
    body = client.get("/api/observability/events", params={"actor": "web"}).json()
    assert [e["op"] for e in body["entries"]] == ["b"]


def test_verify_reports_structure(client, tawn_home):
    from tawn.capability.audit import AuditLog, audit_path

    AuditLog(audit_path(tawn_home)).record("init", "/x", ok=True, actor="cli")
    body = client.get("/api/observability/verify").json()
    assert body["intact"] is True
    assert body["entries"] == 1
    assert body["first_break_index"] is None


def test_spend_groups_and_reports_unpriced(client, db_engine):
    with Session(db_engine) as s:
        s.add(_rollup())
        s.commit()

    body = client.get("/api/observability/spend").json()
    assert body["total_calls"] == 5
    # The total must state its own incompleteness rather than understate.
    assert body["unpriced_calls"] == 2
    assert body["by_operation"][0]["operation"] == "embed"
    assert body["by_provider"][0]["provider"] == "gemini"


def test_spend_status_reports_staleness(client):
    body = client.get("/api/observability/spend/status").json()
    assert "last_reconciled" in body
    assert body["pending_bytes"] >= 0


def test_reconcile_endpoint_runs(client, tawn_home):
    import json

    (tawn_home / "ledger.jsonl").write_text(json.dumps({
        "ts": "2026-07-26T10:00:00+00:00", "provider": "ollama",
        "model": "nomic-embed-text", "tokens_in": 10, "tokens_out": 0,
        "cost_usd": "0", "locality": "local", "sensitive": False, "ok": True,
        "caller": "system", "operation": "embed", "priced": True,
    }) + "\n")

    body = client.post("/api/observability/reconcile").json()
    assert body["entries"] == 1
    assert client.get("/api/observability/spend").json()["total_calls"] == 1


def test_legacy_audit_routes_still_work(client, tawn_home):
    """The Dashboard reads /api/audit — it must keep working, on the right file."""
    from tawn.capability.audit import AuditLog, audit_path

    AuditLog(audit_path(tawn_home)).record("init", "/x", ok=True, actor="cli")
    assert client.get("/api/audit").json()["total"] == 1


def test_spend_is_serialized_as_decimal_strings_not_floats(client, db_engine):
    """`cost_usd` is `Numeric(18, 8)` and its column comment says why: money summed
    through binary floating point drifts. This route used to convert to float and
    then accumulate — the same spend path where reconciliation once found $12.21
    of real spend recorded as $0.0021."""
    import datetime
    from decimal import Decimal

    from sqlalchemy.orm import Session as SASession

    from tawn.memory.schema import ModelCallRollup

    # Three values that cannot be summed exactly in binary floating point.
    with SASession(db_engine) as s:
        for cost in ("0.10", "0.20", "0.30"):
            s.add(ModelCallRollup(
                day=datetime.date(2026, 8, 3), operation="ask", provider="p",
                caller="cli", model="m", calls=1, tokens_in=1, tokens_out=1,
                cost_usd=Decimal(cost), unpriced_calls=0,
            ))
        s.commit()

    body = client.get("/api/observability/spend").json()

    assert isinstance(body["total_cost_usd"], str), "money must not cross as a float"
    assert body["total_cost_usd"] == "0.6", f"got {body['total_cost_usd']}"
    for group in ("by_operation", "by_provider", "by_caller"):
        for row in body[group]:
            assert isinstance(row["cost_usd"], str), f"{group} leaked a float"
    for row in body["by_day"]:
        assert isinstance(row["cost_usd"], str)
