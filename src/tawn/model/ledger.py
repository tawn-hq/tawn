"""Sovereignty ledger — every model call on the record (spec §15.4).

Append-only JSONL at ~/.tawn/ledger.jsonl. Money is Decimal end-to-end,
serialized as strings. Never contains prompt text or keys — only metadata.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

# per-1M-token USD prices: (input, output). Local models cost nothing.
# USD per 1M tokens: (input, output).
#
# Every model a configured provider defaults to must appear here — a test
# asserts it. The bug this guards against is not a wrong price, it is a
# *missing* one: `estimate_cost` used to return 0 for anything absent, so
# six of nine providers silently billed as free and the ledger read $0.0021
# across 28 real calls.
PRICES: dict[str, tuple[Decimal, Decimal]] = {
    # Anthropic
    "claude-opus-4-8": (Decimal("5.00"), Decimal("25.00")),
    "claude-sonnet-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-4-5": (Decimal("1.00"), Decimal("5.00")),
    # OpenAI
    "gpt-5.1": (Decimal("1.25"), Decimal("10.00")),
    # Google — the registry default is flash, but a user can select any of
    # these, and 1,296 real gemini-2.5-pro calls billed as free before they
    # were listed here. Coverage must follow usage, not just defaults.
    #
    # Verified against ai.google.dev/gemini-api/docs/pricing, July 2026.
    # 2.5-pro is tiered: prompts over 200k tokens cost $2.50/$15.00 rather
    # than the rates below, so long-context calls are under-reported. A flat
    # rate keeps the table simple; the `priced` flag is what stops any of
    # this being mistaken for exact billing.
    "gemini-2.5-pro": (Decimal("1.25"), Decimal("10.00")),
    "gemini-2.5-flash": (Decimal("0.30"), Decimal("2.50")),
    "gemini-2.5-flash-lite": (Decimal("0.10"), Decimal("0.40")),
    # Shut down 1 June 2026; priced because historical calls still appear.
    "gemini-2.0-flash": (Decimal("0.10"), Decimal("0.40")),
    # OpenAI-compatible providers
    "deepseek-chat": (Decimal("0.27"), Decimal("1.10")),
    "openai/gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "moonshot-v1-128k": (Decimal("2.00"), Decimal("5.00")),
    "qwen-max": (Decimal("1.60"), Decimal("6.40")),
    "llama-3.3-70b-versatile": (Decimal("0.59"), Decimal("0.79")),
    "grok-3": (Decimal("3.00"), Decimal("15.00")),
    # Mistral. Verified against mistral.ai/pricing: "Mistral Large costs $2/M
    # tokens in and $6/M tokens out." Their smaller models and the OCR
    # endpoint are priced in a JS-rendered table that could not be read from
    # source, so they are deliberately absent — `estimate_cost` reports those
    # calls as unpriced, which is honest, where a guessed figure would not be.
    "mistral-large-latest": (Decimal("2.00"), Decimal("6.00")),
    # Embeddings — input only, so the output price is zero.
    "text-embedding-3-small": (Decimal("0.02"), Decimal("0")),
    "gemini-embedding-001": (Decimal("0.15"), Decimal("0")),
}

# Local models are genuinely free. That is a fact worth recording, and a
# different fact from "no price known".
LOCAL_FREE_MODELS: frozenset[str] = frozenset({
    "nomic-embed-text", "mxbai-embed-large", "bge-m3",
    "snowflake-arctic-embed", "all-minilm",
})


def _is_local_model(model: str) -> bool:
    """True for anything Ollama serves.

    Ollama names carry a `:tag` suffix (`qwen2.5:7b`, `tinyllama:1.1b`), so an
    exact-name set never matched them and they read as "no price known" when
    they are in fact local and genuinely free.
    """
    return model in LOCAL_FREE_MODELS or ":" in model

_M = Decimal(1_000_000)


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> tuple[Decimal, bool]:
    """Return (cost, priced).

    `priced` separates "genuinely free" from "we have no price for this".
    A hardcoded table goes stale as vendors change pricing, so the flag is
    what keeps a total honest rather than merely current — the UI can say
    "$X across N calls, M unpriced" instead of quietly understating spend.
    """
    if _is_local_model(model):
        return Decimal("0"), True
    if model not in PRICES:
        return Decimal("0"), False
    p_in, p_out = PRICES[model]
    return (p_in * tokens_in + p_out * tokens_out) / _M, True


def _fmt(x: Decimal) -> str:
    s = f"{x.normalize():f}"
    return s if s != "-0" else "0"


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)

    def record(
        self,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: Decimal,
        locality: str,
        sensitive: bool,
        ok: bool,
        error: str = "",
        caller: str = "system",
        operation: str = "",
        domain: str | None = None,
        batch_id: str | None = None,
        elapsed_ms: int = 0,
        priced: bool = True,
    ) -> None:
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "provider": provider,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": _fmt(cost_usd),
            "locality": locality,
            "sensitive": bool(sensitive),
            "ok": ok,
            "error": error,
            # Attribution. `caller` reuses the audit log's `actor` vocabulary
            # so the two surfaces can be read together; `operation` is what
            # tells you enrichment cost more than chat.
            "caller": caller,
            "operation": operation,
            "domain": domain,
            "batch_id": batch_id,
            "elapsed_ms": elapsed_ms,
            # False means the cost is a placeholder, not a real figure.
            "priced": priced,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text().splitlines()
            if line.strip()
        ]

    def totals(self) -> dict:
        entries = self.entries()
        local = sum(1 for e in entries if e["locality"] == "local")
        cost = sum((Decimal(e["cost_usd"]) for e in entries), Decimal("0"))
        calls = len(entries)
        pct = _fmt(Decimal(100 * local) / calls) if calls else "100"
        return {
            "calls": calls,
            "local_calls": local,
            "cloud_calls": calls - local,
            "tokens_in": sum(e["tokens_in"] for e in entries),
            "tokens_out": sum(e["tokens_out"] for e in entries),
            "cost_usd": _fmt(cost),
            "local_pct": pct,
        }
