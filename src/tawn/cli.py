"""tawn CLI (Typer). Surface: init, grant, db setup, doctor, wealth."""

import platform

import typer

from tawn.capability.audit import AuditLog
from tawn.capability.grants import DEFAULT_GRANTS_YAML, load_verified
from tawn.capability.integrity import IntegrityError
from tawn.capability.integrity import confirm as integrity_confirm
from tawn.config import settings
from tawn.db import init_db, make_engine
from tawn.dbsetup import INSTALL_HINTS, ensure_database, probe
from tawn.home import init_home, tawn_home

app = typer.Typer(help="Tawn — the twin you own.", invoke_without_command=True)
grant_app = typer.Typer(no_args_is_help=True, help="Inspect and confirm capability grants.")
app.add_typer(grant_app, name="grant")
db_app = typer.Typer(no_args_is_help=True, help="Database bootstrap.")
app.add_typer(db_app, name="db")


@app.callback()
def main(ctx: typer.Context) -> None:
    """Bare `tawn` → branded status screen."""
    if ctx.invoked_subcommand is not None:
        return

    from rich.console import Console
    from rich.padding import Padding

    import tawn
    from tawn.branding import banner, commands_table, status_table

    home = tawn_home()
    initialized = (home / "raw").is_dir()

    grants_ok, grants_detail = True, "deny-all (not initialized)"
    if (home / "grants.yaml").exists():
        try:
            g = load_verified(home / "grants.yaml")
            grants_detail = (
                f"{len(g.read)} read · {len(g.write)} write · "
                f"{len(g.observe)} observe · system {'on' if g.system else 'off'}"
            )
        except IntegrityError:
            grants_ok = False
            grants_detail = "EDITED — run `tawn grant confirm`"
    elif initialized:
        grants_detail = "deny-all"

    db_st = probe(settings().db_url)

    rows = [
        ("home", initialized, str(home) if initialized else "not initialized — run `tawn init`"),
        ("grants", grants_ok, grants_detail),
        ("database", db_st.can_connect, settings().db_url if db_st.can_connect else "unreachable — run `tawn db setup`"),
    ]
    commands = [
        ("tawn setup", "guided setup — start here"),
        ("tawn chat", "talk to your twin"),
        ("tawn model use", "pick which model tawn talks to"),
        ("tawn wealth show", "net worth, allocation, drift"),
        ("tawn web", "local web viewer (all domains)"),
        ("tawn doctor", "health check · `tawn --help` for everything else"),
    ]

    console = Console()
    console.print(Padding(banner(tawn.__version__), (1, 0, 1, 1)))
    console.print(Padding(status_table(rows), (0, 0, 1, 1)))
    console.print(Padding(commands_table(commands), (0, 0, 1, 1)))


@db_app.command("setup")
def db_setup() -> None:
    """Detect postgres, create the tawn database if missing, create tables."""
    url = settings().db_url
    st = ensure_database(url)
    if not st.server_up:
        typer.echo(INSTALL_HINTS, err=True)
        raise typer.Exit(1)
    if not st.can_connect:
        typer.echo(f"server up but cannot connect: {st.detail}", err=True)
        typer.echo("create it manually:  createdb tawn", err=True)
        raise typer.Exit(1)
    init_db(make_engine(url))
    typer.echo(f"database ready ({url})")


wealth_app = typer.Typer(help="Wealth domain — read-only aggregator.")
app.add_typer(wealth_app, name="wealth")


def _mediated_fs():
    from tawn.capability.fs import MediatedFS

    home = tawn_home()
    grants = load_verified(home / "grants.yaml")
    return MediatedFS(grants, AuditLog(home / "audit.log"), home=home)


@wealth_app.command("init")
def wealth_init() -> None:
    """Write the holdings template (never overwrites yours)."""
    from tawn.domains.wealth.holdings import HOLDINGS_TEMPLATE, holdings_path

    home = tawn_home()
    path = holdings_path(home)
    if path.exists():
        typer.echo(f"holdings already at {path} — leaving it alone")
        return
    _mediated_fs().write_text(path, HOLDINGS_TEMPLATE)
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
    holdings = load_holdings(_mediated_fs(), home)
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
        engine, holdings, ngx_prices, us_prices, source, AuditLog(home / "audit.log")
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
    holdings = load_holdings(_mediated_fs(), home)
    engine = make_engine()
    state = latest_snapshot(engine)
    if state is None:
        typer.echo("no snapshots yet — run `tawn wealth snapshot`")
        raise typer.Exit(1)
    Console().print(render_dashboard(state, holdings.targets, snapshot_history(engine)))


@app.command()
def web(port: int = typer.Option(8787, help="port on 127.0.0.1")) -> None:
    """The tawn web viewer — all domains, one local page (spec §16)."""
    import uvicorn

    from tawn.web import create_app

    engine = make_engine()
    typer.echo(f"http://127.0.0.1:{port} — ctrl-c to stop")
    uvicorn.run(create_app(engine), host="127.0.0.1", port=port)


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
    AuditLog(tawn_home() / "audit.log").record(
        "wealth.schedule", f"OnCalendar={every}", ok=ok, detail=msg
    )
    if not ok:
        typer.echo(f"timer not enabled: {msg}", err=True)
        raise typer.Exit(1)
    typer.echo(f"{msg} — snapshots run '{every}', catch up after reboots")


key_app = typer.Typer(no_args_is_help=True, help="Provider API keys (OS keyring).")
app.add_typer(key_app, name="key")


@key_app.command("set")
def key_set(provider: str) -> None:
    """Store a provider key in the OS keyring (prompted, hidden, verified)."""
    from tawn.model.keys import KeyStorageError, set_key

    value = typer.prompt(f"{provider} API key", hide_input=True)
    try:
        set_key(provider, value)
    except KeyStorageError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    typer.echo(f"{provider}: stored in OS keyring (verified)")


@key_app.command("show")
def key_show(provider: str) -> None:
    """Say whether a key is set and where — never prints the value."""
    from tawn.model.keys import key_status

    typer.echo(f"{provider}: {key_status(provider)}")


@app.command()
def ask(
    prompt: str,
    sensitive: bool = typer.Option(
        False, "--sensitive", help="never leaves this machine (local model only)"
    ),
) -> None:
    """Ask your twin. Routes to the best available model (spec §15)."""
    from tawn.model.router import default_router
    from tawn.model.types import Message, ModelError

    router = default_router(tawn_home())
    try:
        r = router.complete([Message(role="user", content=prompt)], sensitive=sensitive)
    except ModelError as e:
        typer.echo(f"model error ({e.kind.value}): {e}", err=True)
        if e.kind.value == "server_error" and not sensitive:
            typer.echo("is ollama running?  ollama serve", err=True)
        raise typer.Exit(1)
    typer.echo(r.text)
    typer.echo(
        f"\n[{r.provider}/{r.model} · {r.tokens_in}→{r.tokens_out} tokens"
        f"{' · sensitive/local' if sensitive else ''}]",
        err=True,
    )


@app.command()
def chat(
    sensitive: bool = typer.Option(
        False, "--sensitive", help="whole session never leaves this machine"
    ),
) -> None:
    """Talk to your twin — history carries across turns. exit/quit to leave."""
    from rich.console import Console
    from rich.markdown import Markdown

    from tawn.model.router import default_router
    from tawn.model.types import Message, ModelError

    console = Console()
    router = default_router(tawn_home())
    names = " → ".join(p.name for p in router.providers)
    console.print(
        f"[dim]tawn chat · providers: {names}"
        f"{' · sensitive (local only)' if sensitive else ''}"
        " · /model switch · /new clear · exit to leave[/dim]"
    )
    history: list[Message] = []
    while True:
        try:
            line = console.input("[bold cyan]you ›[/] ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        line = line.strip()
        if not line:
            continue
        if line.lower() in ("exit", "quit", "/exit", "/quit"):
            break
        if line.lower() in ("/new", "/clear"):
            history.clear()
            console.print("[dim]history cleared[/dim]")
            continue
        if line.lower().startswith("/model"):
            arg = line[len("/model"):].strip()
            target = arg or _pick_model_target()
            if target:
                _set_config("model", target)
                router = default_router(tawn_home())
                console.print(f"[dim]model set to {target}[/dim]")
            continue
        history.append(Message(role="user", content=line))
        try:
            r = router.complete(history, sensitive=sensitive)
        except ModelError as e:
            history.pop()  # failed turn doesn't poison the session
            console.print(f"[red]model error ({e.kind.value}):[/] {e}")
            text = str(e).lower()
            if "not found" in text or "pull" in text:
                console.print("[dim]hint: no local model yet — run `tawn model setup`[/dim]")
            elif "connect" in text:
                console.print("[dim]hint: is ollama running?  ollama serve[/dim]")
            continue
        history.append(Message(role="assistant", content=r.text))
        console.print(Markdown(r.text))
        console.print(
            f"[dim][{r.provider}/{r.model} · {r.tokens_in}→{r.tokens_out} tokens][/dim]"
        )


@app.command("ledger")
def ledger_show() -> None:
    """Sovereignty ledger — where your tokens went, what it cost."""
    from rich.console import Console
    from rich.table import Table

    from tawn.model.ledger import Ledger

    led = Ledger(tawn_home() / "ledger.jsonl")
    entries = led.entries()
    if not entries:
        typer.echo("ledger empty — run `tawn ask` first")
        return
    table = Table(title="model calls (last 20)")
    for col in ("when", "provider", "model", "in", "out", "cost $", "where", "ok"):
        table.add_column(col)
    for e in entries[-20:]:
        table.add_row(
            e["ts"][:19].replace("T", " "),
            e["provider"],
            e["model"],
            str(e["tokens_in"]),
            str(e["tokens_out"]),
            e["cost_usd"],
            e["locality"] + (" 🔒" if e["sensitive"] else ""),
            "✓" if e["ok"] else f"✗ {e['error']}",
        )
    t = led.totals()
    console = Console()
    console.print(table)
    console.print(
        f"{t['calls']} calls · {t['local_pct']}% local · "
        f"{t['tokens_in']}→{t['tokens_out']} tokens · ${t['cost_usd']} spent"
    )


model_app = typer.Typer(no_args_is_help=True, help="Local models (ollama).")
app.add_typer(model_app, name="model")


def _pull_with_progress(provider, name: str) -> None:
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        TextColumn,
        TransferSpeedColumn,
    )

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
    ) as progress:
        task = progress.add_task(name, total=None)

        def on_progress(ev: dict) -> None:
            if ev.get("total"):
                progress.update(
                    task, total=ev["total"], completed=ev.get("completed") or 0,
                    description=f"{name} · {ev.get('status', '')}",
                )

        provider.pull(name, on_progress=on_progress)


@model_app.command("setup")
def model_setup(
    yes: bool = typer.Option(
        False, "--yes", "-y", help="install the recommendation without asking"
    ),
) -> None:
    """Choose and download a local model that fits this machine."""
    from tawn.model.catalog import explore
    from tawn.model.providers.ollama import OllamaProvider, total_ram_bytes
    from tawn.model.types import ModelError

    ram = total_ram_bytes()
    provider = OllamaProvider()
    installed = {m["name"] for m in provider.installed_models()}
    fitting = [r for r in explore(ram, installed) if r["fits"]]
    recommended_idx = next(
        (i for i, r in enumerate(fitting) if r["recommended"]), 0
    )

    typer.echo(f"this machine: {ram // (1024**3)} GB RAM — models that fit:")
    for i, r in enumerate(fitting):
        marks = []
        if r["recommended"]:
            marks.append("recommended")
        if r["installed"]:
            marks.append("installed")
        suffix = f"  ({', '.join(marks)})" if marks else ""
        typer.echo(
            f"  {i + 1:>2}. {r['name']:<28} {r['download_gb']:>5.1f} GB  "
            f"{r['category']:<10} {r['blurb']}{suffix}"
        )

    if yes:
        pick = fitting[recommended_idx]["name"]
    else:
        answer = typer.prompt(
            "which model? [number, or any ollama tag]",
            default=str(recommended_idx + 1),
        ).strip()
        if answer.isdigit() and 1 <= int(answer) <= len(fitting):
            pick = fitting[int(answer) - 1]["name"]
        else:
            pick = answer  # free-form tag, e.g. "gemma3:270m"

    try:
        if provider.has_model(pick):
            typer.echo(f"{pick} already installed")
        else:
            _pull_with_progress(provider, pick)
    except ModelError as e:
        typer.echo(f"{e} — is ollama installed and running? (https://ollama.com)", err=True)
        raise typer.Exit(1)
    _set_local_model(pick)
    typer.echo(f"{pick} is now tawn's local model — try:  tawn chat")


def _set_config(key: str, value: str) -> None:
    """Write one key into ~/.tawn/config.yaml (creates it if needed)."""
    import yaml

    path = tawn_home() / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
    data[key] = value
    path.write_text(yaml.safe_dump(data, sort_keys=True))


def _set_local_model(model: str) -> None:
    _set_config("local_model", model)


def _pick_model_target() -> str | None:
    """Numbered picker over everything usable right now. None = cancelled."""
    from tawn.model.router import model_preference, usable_models

    rows = usable_models(tawn_home())
    if not rows:
        typer.echo(
            "nothing to pick yet — `tawn model setup` for local, "
            "`tawn key set <provider>` for cloud"
        )
        return None
    current = model_preference(tawn_home())
    typer.echo("models you can use right now:")
    for i, r in enumerate(rows):
        mark = "  ← current" if r["target"] == current else ""
        typer.echo(f"  {i + 1:>2}. {r['target']:<40} {r['locality']}{mark}")
    typer.echo("   0. auto (best available, cloud first, local fallback)")
    answer = typer.prompt("which one? [number]", default="0").strip()
    if not answer.isdigit() or int(answer) > len(rows):
        typer.echo("cancelled")
        return None
    return "auto" if int(answer) == 0 else rows[int(answer) - 1]["target"]


@model_app.command("use")
def model_use(
    target: str = typer.Argument(
        "", help="provider/model (e.g. anthropic/claude-haiku-4-5), a local tag, or 'auto'. Empty = picker."
    ),
) -> None:
    """Choose which model tawn talks to (`auto` = failover chain)."""
    if not target:
        picked = _pick_model_target()
        if picked is None:
            raise typer.Exit(0)
        target = picked
    _set_config("model", target)
    typer.echo(f"model set to {target} — chat and ask use it now")


@model_app.command("pull")
def model_pull(name: str) -> None:
    """Download any ollama model by tag, e.g. `tawn model pull gemma3:4b`."""
    from tawn.model.providers.ollama import OllamaProvider
    from tawn.model.types import ModelError

    try:
        _pull_with_progress(OllamaProvider(), name)
    except ModelError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    typer.echo(f"{name} ready")


@model_app.command("list")
def model_list() -> None:
    """Installed local models, plus cloud models your keys unlock."""
    from tawn.model.keys import get_key
    from tawn.model.providers.ollama import OllamaProvider

    installed = OllamaProvider().installed_models()
    if installed:
        typer.echo("local (ollama):")
        for m in installed:
            typer.echo(f"  {m['name']}  {m['size'] / 1024**3:.1f} GB")
    else:
        typer.echo("local: none (daemon down or nothing pulled — `tawn model setup`)")
    key = get_key("gemini")
    if key:
        from tawn.model.providers.gemini import GeminiProvider

        cloud = GeminiProvider(api_key=key).available_models()
        typer.echo(f"cloud (gemini, {len(cloud)} models):")
        for m in cloud[:10]:
            typer.echo(f"  {m['name']}  ({m['context_tokens'] // 1000}k ctx)")
        if len(cloud) > 10:
            typer.echo(f"  … {len(cloud) - 10} more")
    else:
        typer.echo("cloud: no keys set (`tawn key set gemini`)")


@model_app.command("explore")
def model_explore(
    live: bool = typer.Option(
        False, "--live", help="full ollama.com directory (needs network)"
    ),
    category: str = typer.Option(
        "", "--category", help="filter: chat, code, reasoning, vision, embedding"
    ),
) -> None:
    """What could this machine run? Curated picks, or --live for everything."""
    from rich.console import Console
    from rich.table import Table

    from tawn.model.catalog import explore
    from tawn.model.providers.ollama import OllamaProvider, total_ram_bytes

    ram = total_ram_bytes()
    installed = {m["name"] for m in OllamaProvider().installed_models()}
    source = "curated"
    if live:
        from tawn.model.directory import live_explore

        try:
            rows = live_explore(ram, installed)
            source = "ollama.com directory"
        except Exception as e:
            typer.echo(f"directory unreachable ({type(e).__name__}) — using curated list", err=True)
            rows = explore(ram, installed)
    else:
        rows = explore(ram, installed)
    if category:
        rows = [r for r in rows if r["category"] == category]

    table = Table(
        title=f"models for this machine ({ram // 1024**3} GB RAM) — {source}"
    )
    for col in ("model", "download", "needs RAM", "fits", "", "about"):
        table.add_column(col)
    for r in rows:
        mark = "★ recommended" if r["recommended"] else (
            "installed" if r["installed"] else ""
        )
        table.add_row(
            r["name"],
            f"{r['download_gb']:.1f} GB",
            f"{r['min_ram_gb']:.0f} GB",
            "✓" if r["fits"] else "✗",
            mark,
            r["blurb"],
        )
    Console().print(table)
    typer.echo("download any of them:  tawn model pull <name>")


@app.command()
def setup() -> None:
    """Guided setup: home → database → local model → cloud keys. Safe to re-run."""
    typer.echo("tawn setup — Enter accepts the default at every step\n")

    typer.echo("· step 1/4 — home directory")
    init()

    typer.echo("\n· step 2/4 — database (stores snapshots and memory)")
    if typer.confirm("set up postgres now?", default=True):
        try:
            db_setup()
        except typer.Exit:
            typer.echo("skipped — run `tawn db setup` when postgres is ready")

    typer.echo("\n· step 3/4 — local model (private, free, works offline)")
    if typer.confirm("download a local model?", default=True):
        try:
            model_setup(yes=False)
        except typer.Exit:
            typer.echo("skipped — run `tawn model setup` once ollama is installed")

    typer.echo("\n· step 4/4 — cloud models (optional, smarter, needs a key)")
    while typer.confirm("add a cloud API key?", default=False):
        provider = typer.prompt("provider (anthropic / openai / gemini / deepseek)").strip()
        try:
            key_set(provider)
        except typer.Exit:
            typer.echo(f"{provider}: not stored — try again or use an env var")

    typer.echo("\nall set — talk to your twin:  tawn chat")


@app.command()
def doctor() -> None:
    """Health checks: python, home, grants, database."""
    home = tawn_home()
    checks: list[tuple[str, bool, str]] = []
    checks.append(("python >= 3.12", True, platform.python_version()))
    checks.append(("home initialized", (home / "raw").is_dir(), str(home)))
    grants_ok = True
    grants_detail = "deny-all (no grants.yaml)"
    if (home / "grants.yaml").exists():
        try:
            load_verified(home / "grants.yaml")
            grants_detail = "confirmed"
        except IntegrityError as e:
            grants_ok = False
            grants_detail = str(e)
    checks.append(("grants integrity", grants_ok, grants_detail))
    st = probe(settings().db_url)
    checks.append(("database reachable", st.can_connect, settings().db_url))
    failed = False
    for name, ok, detail in checks:
        mark = "ok " if ok else "FAIL"
        if not ok:
            failed = True
        typer.echo(f"[{mark}] {name} — {detail}")
    raise typer.Exit(1 if failed else 0)


@app.command()
def init() -> None:
    """Create ~/.tawn with deny-all grants. Safe to re-run."""
    home = tawn_home()
    created = init_home(home)
    grants_path = home / "grants.yaml"
    if not grants_path.exists():
        grants_path.write_text(DEFAULT_GRANTS_YAML)
        integrity_confirm(grants_path)
        typer.echo(f"wrote deny-all {grants_path}")
    audit = AuditLog(home / "audit.log")
    audit.record("init", str(home), ok=True, detail=f"{len(created)} dirs created")
    typer.echo(
        f"tawn home ready at {home} (deny-all; edit grants.yaml, then `tawn grant confirm`)"
    )
    typer.echo(
        "optional: add a cloud model key with `tawn key set gemini` "
        "(stored in the OS keyring — local Ollama needs no key)"
    )


def _fmt_paths(paths) -> str:
    return ", ".join(str(p) for p in paths) if paths else "(none)"


@grant_app.command("list")
def grant_list() -> None:
    """Show the current capability surface."""
    home = tawn_home()
    try:
        g = load_verified(home / "grants.yaml")
    except IntegrityError as e:
        typer.echo(f"integrity: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"read: {_fmt_paths(g.read)}")
    typer.echo(f"write: {_fmt_paths(g.write)}")
    typer.echo(f"observe: {', '.join(g.observe) or '(none)'}")
    typer.echo(f"system: {'on' if g.system else 'off'}")
    typer.echo(f"mcp: {', '.join(g.mcp) or '(none)'}")


@grant_app.command("confirm")
def grant_confirm() -> None:
    """Accept a hand-edited grants.yaml (re-hash the integrity sidecar)."""
    home = tawn_home()
    grants_path = home / "grants.yaml"
    if not grants_path.exists():
        typer.echo("no grants.yaml — run `tawn init` first", err=True)
        raise typer.Exit(1)
    digest = integrity_confirm(grants_path)
    AuditLog(home / "audit.log").record(
        "grant.confirm", str(grants_path), ok=True, detail=digest
    )
    typer.echo(f"confirmed grants.yaml ({digest[:12]}…)")
