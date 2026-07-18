"""Rich rendering for `tawn wealth`. Pure functions in, renderables out —
the CLI does the printing, tests read the export."""

from datetime import datetime
from decimal import Decimal

from rich.console import Group
from rich.table import Table

from tawn.branding import BONE, LAPIS, MUTED


def compute_drift(state: dict, targets: dict[str, Decimal]) -> list[dict]:
    out = []
    for cls, info in state["classes"].items():
        actual = Decimal(info["pct"])
        target = targets.get(cls, Decimal(0))
        out.append(
            {
                "class": cls,
                "actual_pct": str(actual),
                "target_pct": str(target),
                "drift": str(actual - target),
            }
        )
    return out


def render_dashboard(
    state: dict, targets: dict[str, Decimal], history: list[tuple[datetime, Decimal]]
) -> Group:
    alloc = Table(
        title=f"net worth ₦{state['total_ngn']}  ·  prices: {state['price_source']}",
        title_style=f"bold {BONE}",
        header_style=MUTED,
        border_style=MUTED,
    )
    alloc.add_column("class", style=f"bold {LAPIS}")
    alloc.add_column("value ₦", justify="right")
    alloc.add_column("actual %", justify="right")
    alloc.add_column("target %", justify="right")
    alloc.add_column("drift", justify="right")
    for d in compute_drift(state, targets):
        info = state["classes"][d["class"]]
        drift = Decimal(d["drift"])
        style = "red" if abs(drift) > 5 else "green"
        alloc.add_row(
            d["class"],
            info["value_ngn"],
            d["actual_pct"],
            d["target_pct"],
            f"[{style}]{drift:+}[/{style}]",
        )
    renderables: list = [alloc]
    if history:
        hist = Table(title="history", title_style=MUTED, header_style=MUTED, border_style=MUTED)
        hist.add_column("asof")
        hist.add_column("total ₦", justify="right")
        for asof, total in history:
            hist.add_row(asof.date().isoformat(), str(total))
        renderables.append(hist)
    return Group(*renderables)
