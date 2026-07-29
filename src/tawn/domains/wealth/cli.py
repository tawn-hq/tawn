"""Wealth domain CLI — read-only aggregator. Moved out of tawn.cli as
part of the domain plugin migration; behavior unchanged."""

import typer

from tawn.capability.audit import AuditLog, audit_path
from tawn.db import init_db, make_engine
from tawn.domains.base import mediated_fs
from tawn.home import tawn_home

wealth_app = typer.Typer(help="Wealth domain — read-only aggregator.")


@wealth_app.command("init")
def wealth_init() -> None:
    """Write the holdings template (never overwrites yours)."""
    from tawn.domains.wealth.holdings import HOLDINGS_TEMPLATE, holdings_path

    home = tawn_home()
    path = holdings_path(home)
    if path.exists():
        typer.echo(f"holdings already at {path} — leaving it alone")
        return
    mediated_fs().write_text(path, HOLDINGS_TEMPLATE)
    typer.echo(f"wrote template {path} — fill in your positions")


@wealth_app.command("snapshot")
def wealth_snapshot(
    offline: bool = typer.Option(False, "--offline", help="manual prices only")
) -> None:
    """Value holdings (NGX + US + usd/land/cash) and store a snapshot."""
    from tawn.domains.wealth.holdings import load_holdings
    from tawn.domains.wealth.prices import (
        ManualPrices,
        NgxPriceSource,
        StooqPriceSource,
        fetch_or_fallback,
    )
    from tawn.domains.wealth.snapshot import take_snapshot

    home = tawn_home()
    holdings = load_holdings(mediated_fs(), home)
    ngx_tickers = [p.ticker for p in holdings.ngx]
    us_tickers = [p.ticker for p in holdings.us]
    ngx_manual = ManualPrices(holdings.ngx)
    us_manual = ManualPrices(holdings.us)
    if offline:
        ngx_prices, ngx_src = ngx_manual.get_prices(ngx_tickers), "manual"
        us_prices, us_src = us_manual.get_prices(us_tickers), "manual"
    else:
        ngx_prices, ngx_src = fetch_or_fallback(NgxPriceSource(), ngx_manual, ngx_tickers)
        us_prices, us_src = fetch_or_fallback(StooqPriceSource(), us_manual, us_tickers)
    source = ngx_src if ngx_src == us_src else f"ngx:{ngx_src} us:{us_src}"
    engine = make_engine()
    init_db(engine)
    state = take_snapshot(
        engine, holdings, ngx_prices, us_prices, source, AuditLog(audit_path(home))
    )
    typer.echo(f"snapshot stored — total ₦{state['total_ngn']} (prices: {source})")


@wealth_app.command("show")
def wealth_show() -> None:
    """Latest snapshot as a dashboard."""
    from rich.console import Console

    from tawn.domains.wealth.dashboard import render_dashboard
    from tawn.domains.wealth.holdings import load_holdings
    from tawn.domains.wealth.snapshot import latest_snapshot, snapshot_history

    home = tawn_home()
    holdings = load_holdings(mediated_fs(), home)
    engine = make_engine()
    state = latest_snapshot(engine)
    if state is None:
        typer.echo("no snapshots yet — run `tawn wealth snapshot`")
        raise typer.Exit(1)
    Console().print(render_dashboard(state, holdings.targets, snapshot_history(engine)))


@wealth_app.command("schedule")
def wealth_schedule(
    every: str = typer.Option(
        "daily", help="systemd OnCalendar spec, e.g. daily, hourly, '*-*-* 18:00:00'"
    )
) -> None:
    """Keep snapshots fresh in the background (systemd user timer)."""
    import shutil as _shutil
    import sys

    from tawn.domains.wealth.schedule import enable_timer, write_units

    tawn_bin = _shutil.which("tawn") or sys.argv[0]
    files = write_units(tawn_bin, every)
    for f in files:
        typer.echo(f"wrote {f}")
    ok, msg = enable_timer()
    AuditLog(audit_path(tawn_home())).record(
        "wealth.schedule", f"OnCalendar={every}", ok=ok, detail=msg, actor="cli"
    )
    if not ok:
        typer.echo(f"timer not enabled: {msg}", err=True)
        raise typer.Exit(1)
    typer.echo(f"{msg} — snapshots run '{every}', catch up after reboots")
