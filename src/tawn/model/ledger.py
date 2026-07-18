"""Sovereignty ledger — every model call on the record (spec §15.4).

Append-only JSONL at ~/.tawn/ledger.jsonl. Money is Decimal end-to-end,
serialized as strings. Never contains prompt text or keys — only metadata.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

# per-1M-token USD prices: (input, output). Local models cost nothing.
PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "gemini-2.5-flash": (Decimal("0.30"), Decimal("2.50")),
    "gemini-2.5-flash-lite": (Decimal("0.10"), Decimal("0.40")),
    "claude-opus-4-8": (Decimal("5.00"), Decimal("25.00")),
    "claude-sonnet-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-4-5": (Decimal("1.00"), Decimal("5.00")),
    "gpt-5.1": (Decimal("1.25"), Decimal("10.00")),
    "deepseek-chat": (Decimal("0.27"), Decimal("1.10")),
}

_M = Decimal(1_000_000)


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    if model not in PRICES:
        return Decimal("0")
    p_in, p_out = PRICES[model]
    return (p_in * tokens_in + p_out * tokens_out) / _M


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
    ) -> None:
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "provider": provider,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": _fmt(cost_usd),
            "locality": locality,
            "sensitive": sensitive,
            "ok": ok,
            "error": error,
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
