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
    cost, priced = estimate_cost("gemini-2.5-flash", 1_000_000, 1_000_000)
    assert cost == Decimal("2.80")
    assert priced is True


def test_estimate_cost_unknown_model_is_zero_but_flagged_unpriced():
    """Superseded contract: this used to return a bare Decimal("0").

    That made "free" and "we have no price" indistinguishable, which is how
    six of nine configured providers billed as free.
    """
    # NB: not an Ollama-style name — anything with a `:tag` is local and
    # genuinely free, which is a different fact from "no price known".
    cost, priced = estimate_cost("some-vendor-model-we-do-not-track", 999, 999)
    assert cost == Decimal("0")
    assert priced is False


def test_record_persists_attribution(tmp_path):
    from decimal import Decimal

    from tawn.model.ledger import Ledger

    led = Ledger(tmp_path / "ledger.jsonl")
    led.record(
        provider="gemini", model="gemini-2.5-flash", tokens_in=10, tokens_out=5,
        cost_usd=Decimal("0.001"), locality="cloud", sensitive=False, ok=True,
        caller="cli", operation="enrich.chunk", domain="work",
        batch_id="b1", elapsed_ms=1234, priced=True,
    )
    e = led.entries()[-1]
    assert e["caller"] == "cli"
    assert e["operation"] == "enrich.chunk"
    assert e["domain"] == "work"
    assert e["batch_id"] == "b1"
    assert e["elapsed_ms"] == 1234
    assert e["priced"] is True


def test_entries_written_before_this_stage_lack_attribution(tmp_path):
    """Older lines have none of these fields; never backfill a guess."""
    import json

    from tawn.model.ledger import Ledger

    p = tmp_path / "ledger.jsonl"
    p.write_text(json.dumps({
        "ts": "2026-07-01T00:00:00+00:00", "provider": "gemini",
        "model": "gemini-2.5-flash", "tokens_in": 1, "tokens_out": 1,
        "cost_usd": "0.0", "locality": "cloud", "sensitive": False, "ok": True,
    }) + "\n")
    e = Ledger(p).entries()[-1]
    assert e.get("caller", "unknown") == "unknown"
    assert e.get("priced") is None


def test_router_tags_calls_with_its_attribution(tmp_path):
    """Spend must be traceable to what asked for it, not just the provider."""
    from decimal import Decimal

    from tawn.model.ledger import Ledger
    from tawn.model.router import Router
    from tawn.model.types import Message, ModelResponse

    class FakeProvider:
        name = "gemini"
        locality = "cloud"
        model = "gemini-2.5-flash"

        def complete(self, msgs):
            return ModelResponse(text="hi", model=self.model, provider=self.name,
                                 tokens_in=10, tokens_out=5)

    led = Ledger(tmp_path / "ledger.jsonl")
    r = Router([FakeProvider()], led, caller="web", operation="chat", domain="work")
    r.complete([Message(role="user", content="hello")])

    e = led.entries()[-1]
    assert e["caller"] == "web"
    assert e["operation"] == "chat"
    assert e["domain"] == "work"
    assert e["priced"] is True
