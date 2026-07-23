from decimal import Decimal

from rich.console import Console

from tawn.domains.wealth.dashboard import compute_drift, render_dashboard

STATE = {
    "total_ngn": "25000",
    "classes": {
        "ngx": {"value_ngn": "5000", "pct": "20"},
        "us": {"value_ngn": "5000", "pct": "20"},
        "usd": {"value_ngn": "10000", "pct": "40"},
        "land": {"value_ngn": "3000", "pct": "12"},
        "cash": {"value_ngn": "2000", "pct": "8"},
    },
    "positions": [],
    "price_source": "manual",
}
TARGETS = {
    "ngx": Decimal(30),
    "us": Decimal(10),
    "usd": Decimal(30),
    "land": Decimal(20),
    "cash": Decimal(10),
}


def test_compute_drift_signs():
    drift = {d["class"]: Decimal(d["drift"]) for d in compute_drift(STATE, TARGETS)}
    assert drift["ngx"] == Decimal("-10")  # under target
    assert drift["us"] == Decimal("10")    # over target
    assert drift["usd"] == Decimal("10")


def test_render_dashboard_contains_key_figures():
    console = Console(record=True, width=100)
    console.print(render_dashboard(STATE, TARGETS, history=[]))
    out = console.export_text()
    assert "25000" in out          # total
    assert "ngx" in out and "us" in out and "usd" in out
    assert "manual" in out         # price source shown
