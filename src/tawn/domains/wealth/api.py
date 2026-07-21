"""Wealth domain web API — the generic view endpoint every domain
implements, plus the richer endpoints the wealth page's history chart
needs. Each handler builds its own engine (matches the existing CLI
convention of calling make_engine() per invocation)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from tawn.db import make_engine
from tawn.domains.wealth.snapshot import latest_snapshot, snapshot_history

router = APIRouter()

@router.get("/view")
def view():
    engine = make_engine()
    state = latest_snapshot(engine)
    if state is None:
        return {
            "title": "Wealth",
            "sections": [{"type": "empty", "message": "no snapshots yet — run `tawn wealth snapshot`"}],
        }
    rows = [
        [cls, info["value_ngn"], f"{info['pct']}%"]
        for cls, info in state["classes"].items()
    ]
    return {
        "title": "Wealth",
        "stat": {
            "label": "Net worth",
            "value": f"₦{state['total_ngn']}",
            "sublabel": f"prices: {state['price_source']}",
        },
        "sections": [{"type": "table", "columns": ["class", "value ₦", "%"], "rows": rows}],
    }


@router.get("/latest")
def latest():
    engine = make_engine()
    state = latest_snapshot(engine)
    if state is None:
        return JSONResponse({"error": "no snapshots yet"}, status_code=404)
    return state


@router.get("/history")
def history():
    engine = make_engine()
    points = snapshot_history(engine)
    return [{"asof": asof.isoformat(), "total_ngn": str(total)} for asof, total in points]
