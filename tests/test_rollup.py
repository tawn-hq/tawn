import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.memory.schema import Base, LedgerWatermark, ModelCallRollup
from tawn.model.rollup import reconcile


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _entry(**kw):
    base = {
        "ts": "2026-07-26T10:00:00+00:00", "provider": "gemini",
        "model": "gemini-2.5-flash", "tokens_in": 100, "tokens_out": 50,
        "cost_usd": "0.00012500", "locality": "cloud", "sensitive": False,
        "ok": True, "error": "", "caller": "cli", "operation": "chat",
        "domain": "work", "batch_id": None, "elapsed_ms": 10, "priced": True,
    }
    base.update(kw)
    return json.dumps(base)


def _write(home, lines):
    (home / "ledger.jsonl").write_text("\n".join(lines) + "\n")


def test_aggregates_entries(tmp_path, db):
    _write(tmp_path, [_entry(), _entry()])
    res = reconcile(tmp_path, db)
    assert res["entries"] == 2
    row = db.query(ModelCallRollup).one()
    assert row.calls == 2
    assert row.tokens_in == 200
    assert row.cost_usd == Decimal("0.00025000")


def test_rerun_is_a_noop(tmp_path, db):
    _write(tmp_path, [_entry()])
    reconcile(tmp_path, db)
    assert reconcile(tmp_path, db)["entries"] == 0
    assert db.query(ModelCallRollup).one().calls == 1


def test_watermark_stops_at_last_newline(tmp_path, db):
    """A crash mid-append leaves a partial line; it must not be consumed."""
    good = _entry()
    (tmp_path / "ledger.jsonl").write_text(good + "\n" + '{"ts": "2026-07-26T11:00')

    res = reconcile(tmp_path, db)
    assert res["entries"] == 1
    assert res["offset"] == len(good) + 1

    # Once the writer finishes the line, the next pass picks it up.
    (tmp_path / "ledger.jsonl").write_text(good + "\n" + _entry(operation="embed") + "\n")
    assert reconcile(tmp_path, db)["entries"] == 1
    assert {r.operation for r in db.query(ModelCallRollup).all()} == {"chat", "embed"}


def test_unpriced_calls_are_counted(tmp_path, db):
    """A model no table covers stays unpriced — repricing cannot rescue it."""
    _write(tmp_path, [_entry(model="unknown-vendor-model", priced=False, cost_usd="0.00000000")])
    reconcile(tmp_path, db)
    assert db.query(ModelCallRollup).one().unpriced_calls == 1


def test_truncated_file_rescans(tmp_path, db):
    _write(tmp_path, [_entry(), _entry()])
    reconcile(tmp_path, db)
    _write(tmp_path, [_entry(operation="recall")])
    assert reconcile(tmp_path, db)["entries"] == 1


def test_rebuild_matches_incremental(tmp_path, db):
    _write(tmp_path, [_entry(), _entry(operation="embed")])
    reconcile(tmp_path, db)
    incremental = {(r.operation, r.calls) for r in db.query(ModelCallRollup).all()}

    reconcile(tmp_path, db, rebuild=True)
    assert {(r.operation, r.calls) for r in db.query(ModelCallRollup).all()} == incremental


def test_missing_file_is_not_an_error(tmp_path, db):
    assert reconcile(tmp_path, db)["entries"] == 0


def test_malformed_line_is_skipped_not_fatal(tmp_path, db):
    _write(tmp_path, [_entry(), "{not json", _entry()])
    assert reconcile(tmp_path, db)["entries"] == 2


def test_cost_precision_over_many_small_entries(tmp_path, db):
    """Money must not drift — Decimal end to end, never float."""
    _write(tmp_path, [_entry(cost_usd="0.00000001") for _ in range(1000)])
    reconcile(tmp_path, db)
    assert db.query(ModelCallRollup).one().cost_usd == Decimal("0.00001000")


def test_watermark_records_progress(tmp_path, db):
    _write(tmp_path, [_entry(), _entry()])
    reconcile(tmp_path, db)
    wm = db.query(LedgerWatermark).one()
    assert wm.entries_seen == 2
    assert wm.byte_offset > 0


def test_entries_without_priced_field_count_as_unpriced(tmp_path, db):
    """Absent is unknown, not priced.

    Ledger lines written before attribution existed have no `priced` key.
    Treating them as priced let 1,296 real calls read as free with nothing
    flagged.
    """
    import json

    # A model nothing can price: repricing from tokens is impossible, so the
    # missing flag genuinely means unknown.
    (tmp_path / "ledger.jsonl").write_text(json.dumps({
        "ts": "2026-07-26T10:00:00+00:00", "provider": "mystery",
        "model": "unknown-vendor-model", "tokens_in": 100, "tokens_out": 50,
        "cost_usd": "0", "locality": "cloud", "sensitive": False, "ok": True,
    }) + "\n")

    reconcile(tmp_path, db)
    assert db.query(ModelCallRollup).one().unpriced_calls == 1


def test_legacy_entry_with_real_cost_counts_as_priced(tmp_path, db):
    """A non-zero cost was computed from a real price."""
    import json

    (tmp_path / "ledger.jsonl").write_text(json.dumps({
        "ts": "2026-07-26T10:00:00+00:00", "provider": "openai",
        "model": "gpt-5.1", "tokens_in": 100, "tokens_out": 50,
        "cost_usd": "0.0031", "locality": "cloud", "sensitive": False, "ok": True,
    }) + "\n")
    reconcile(tmp_path, db)
    assert db.query(ModelCallRollup).one().unpriced_calls == 0


def test_legacy_local_entry_counts_as_priced(tmp_path, db):
    """Local models are genuinely free, not unknown."""
    import json

    (tmp_path / "ledger.jsonl").write_text(json.dumps({
        "ts": "2026-07-26T10:00:00+00:00", "provider": "ollama",
        "model": "tinyllama:1.1b", "tokens_in": 100, "tokens_out": 50,
        "cost_usd": "0", "locality": "local", "sensitive": False, "ok": True,
    }) + "\n")
    reconcile(tmp_path, db)
    assert db.query(ModelCallRollup).one().unpriced_calls == 0


def test_reprices_entries_written_before_the_model_had_a_price(tmp_path, db):
    """The ledger is append-only, so a $0 line stays $0 — but the tokens
    are recorded, so the derived view can recover the real cost."""
    import json

    (tmp_path / "ledger.jsonl").write_text(json.dumps({
        "ts": "2026-07-26T10:00:00+00:00", "provider": "gemini",
        "model": "gemini-2.5-pro", "tokens_in": 1_000_000, "tokens_out": 0,
        "cost_usd": "0", "locality": "cloud", "sensitive": False, "ok": True,
    }) + "\n")

    reconcile(tmp_path, db)
    row = db.query(ModelCallRollup).one()
    assert row.cost_usd == Decimal("1.25")     # priced from tokens
    assert row.unpriced_calls == 0


def test_recorded_cost_always_wins_over_recomputation(tmp_path, db):
    """What the provider was charged beats what we would estimate now."""
    import json

    (tmp_path / "ledger.jsonl").write_text(json.dumps({
        "ts": "2026-07-26T10:00:00+00:00", "provider": "openai",
        "model": "gpt-5.1", "tokens_in": 1_000_000, "tokens_out": 0,
        "cost_usd": "9.99", "locality": "cloud", "sensitive": False, "ok": True,
    }) + "\n")

    reconcile(tmp_path, db)
    assert db.query(ModelCallRollup).one().cost_usd == Decimal("9.99")


def test_genuinely_unknown_model_stays_unpriced(tmp_path, db):
    import json

    (tmp_path / "ledger.jsonl").write_text(json.dumps({
        "ts": "2026-07-26T10:00:00+00:00", "provider": "mystery",
        "model": "some-unknown-model", "tokens_in": 1000, "tokens_out": 0,
        "cost_usd": "0", "locality": "cloud", "sensitive": False, "ok": True,
    }) + "\n")

    reconcile(tmp_path, db)
    assert db.query(ModelCallRollup).one().unpriced_calls == 1
