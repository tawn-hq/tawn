import json
from decimal import Decimal

from tawn.model.ledger import PRICES, Ledger, estimate_cost


def test_record_appends_jsonl(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.record(
        provider="ollama", model="qwen2.5:7b", tokens_in=10, tokens_out=5,
        cost_usd=Decimal("0"), locality="local", sensitive=False, ok=True,
    )
    led.record(
        provider="gemini", model="gemini-2.5-flash", tokens_in=100, tokens_out=40,
        cost_usd=Decimal("0.000026"), locality="cloud", sensitive=False, ok=True,
    )
    lines = (tmp_path / "ledger.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["provider"] == "ollama" and first["ok"] is True
    assert first["cost_usd"] == "0"  # Decimal serialized as string
    assert "ts" in first


def test_entries_round_trip(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.record(
        provider="gemini", model="gemini-2.5-flash", tokens_in=1, tokens_out=1,
        cost_usd=Decimal("0.01"), locality="cloud", sensitive=False, ok=False,
        error="rate_limit",
    )
    (e,) = led.entries()
    assert e["error"] == "rate_limit" and e["ok"] is False


def test_entries_empty_when_no_file(tmp_path):
    assert Ledger(tmp_path / "ledger.jsonl").entries() == []


def test_totals_split_local_cloud(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    for _ in range(3):
        led.record(
            provider="ollama", model="qwen2.5:7b", tokens_in=10, tokens_out=5,
            cost_usd=Decimal("0"), locality="local", sensitive=False, ok=True,
        )
    led.record(
        provider="gemini", model="gemini-2.5-flash", tokens_in=100, tokens_out=40,
        cost_usd=Decimal("0.5"), locality="cloud", sensitive=False, ok=True,
    )
    t = led.totals()
    assert t["calls"] == 4
    assert t["local_calls"] == 3 and t["cloud_calls"] == 1
    assert t["tokens_in"] == 130 and t["tokens_out"] == 55
    assert t["cost_usd"] == "0.5"
    assert t["local_pct"] == "75"


def test_estimate_cost_gemini_flash():
    # per-1M prices: (0.30 in, 2.50 out)
    assert "gemini-2.5-flash" in PRICES
    cost = estimate_cost("gemini-2.5-flash", 1_000_000, 1_000_000)
    assert cost == Decimal("2.80")


def test_estimate_cost_unknown_model_is_zero():
    assert estimate_cost("qwen2.5:7b", 999, 999) == Decimal("0")
