"""Tawn web viewer — the global local surface (design spec §16).

One app for the whole twin, served on 127.0.0.1 by `tawn web`.
Stage 1 ships the shell + the wealth view; Stage 6 adds wiki,
backlinks, and the entity graph onto this same app. Read-only:
edits always go through the write-back path, never HTML forms.

Styling = brand tokens (Sandstone & Lapis), self-contained pages.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.engine import Engine

from tawn.domains.wealth.snapshot import latest_snapshot, snapshot_history

_SHELL_CSS = """
  :root { --bg:#FAF7F1; --text:#33291C; --line:#E7E0D2; --lapis:#2E5FA3; --muted:#6B5F4B; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#191510; --text:#EFE9DC; --line:#383021; --lapis:#4A7BC8; --muted:#ADA28C; }
  }
  body { background:var(--bg); color:var(--text); font:16px/1.5 system-ui,sans-serif;
         max-width:640px; margin:40px auto; padding:0 20px; }
  h1 { font-size:20px; } h1 b { color:var(--lapis); }
  h1 a { color:inherit; text-decoration:none; }
  .total { font-size:40px; font-weight:800; letter-spacing:-0.02em; }
  table { border-collapse:collapse; width:100%; margin-top:20px; }
  th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); }
  td.n { text-align:right; font-variant-numeric:tabular-nums; }
  .muted { color:var(--muted); font-size:13px; }
  .card { border:1px solid var(--line); border-radius:12px; padding:16px 20px;
          margin-top:16px; display:block; color:inherit; text-decoration:none; }
  .card:hover { border-color:var(--lapis); }
  .card b { color:var(--lapis); }
"""

_HOME = """<!doctype html>
<html><head><meta charset="utf-8"><title>tawn</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{css}</style></head><body>
<h1>taw<b>n</b> <span class="muted">the twin you own · 127.0.0.1 only</span></h1>
<a class="card" href="/wealth"><b>wealth</b><br>
<span class="muted">{wealth_line}</span></a>
<p class="muted">work · research · academic arrive with their domains.
wiki + entity graph arrive at stage 6.</p>
</body></html>"""

_WEALTH = """<!doctype html>
<html><head><meta charset="utf-8"><title>tawn · wealth</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{css}</style></head><body>
<h1><a href="/">taw<b>n</b></a> · wealth <span class="muted">read-only</span></h1>
<div class="total">₦{total}</div>
<div class="muted">prices: {source}</div>
<table><tr><th>class</th><th style="text-align:right">value ₦</th><th style="text-align:right">%</th></tr>
{rows}
</table>
<p class="muted">history: {points} snapshots</p>
</body></html>"""


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="tawn", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def home():
        state = latest_snapshot(engine)
        line = (
            f"net worth ₦{state['total_ngn']}"
            if state
            else "no snapshots yet — run `tawn wealth snapshot`"
        )
        return HTMLResponse(_HOME.format(css=_SHELL_CSS, wealth_line=line))

    @app.get("/api/wealth/latest")
    def api_wealth_latest():
        state = latest_snapshot(engine)
        if state is None:
            return JSONResponse({"error": "no snapshots yet"}, status_code=404)
        return state

    @app.get("/wealth", response_class=HTMLResponse)
    def wealth():
        state = latest_snapshot(engine)
        if state is None:
            return HTMLResponse(
                "<p>no snapshots yet — run <code>tawn wealth snapshot</code></p>"
            )
        rows = "\n".join(
            f'<tr><td>{cls}</td><td class="n">{info["value_ngn"]}</td>'
            f'<td class="n">{info["pct"]}</td></tr>'
            for cls, info in state["classes"].items()
        )
        return HTMLResponse(
            _WEALTH.format(
                css=_SHELL_CSS,
                total=state["total_ngn"],
                source=state["price_source"],
                rows=rows,
                points=len(snapshot_history(engine)),
            )
        )

    return app
