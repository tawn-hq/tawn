"""tawn CLI (Typer). Surface: init, grant, db setup, doctor, wealth."""

import platform
from pathlib import Path

import typer
from typer.core import TyperGroup

from tawn.capability.audit import AuditLog
from tawn.capability.grants import DEFAULT_GRANTS_YAML, load_verified
from tawn.capability.integrity import IntegrityError
from tawn.capability.integrity import confirm as integrity_confirm
from tawn.config import settings
from tawn.db import init_db, make_engine
from tawn.dbsetup import INSTALL_HINTS, ensure_database, probe
from tawn.home import init_home, tawn_home
from tawn.memory.note import note
from tawn.memory.recall import recall
from tawn.memory.brief import brief
from tawn.compiler.compiler import run_compile, compile_status

class _DomainAwareGroup(TyperGroup):
    """Refreshes domain subcommands from the registry on every dispatch
    instead of freezing them at module-import time. A plain `for domain in
    enabled_domains(): app.add_typer(...)` loop only runs once — correct
    for a real `tawn` process (one shot), but stale across multiple
    invocations sharing one interpreter (e.g. the test suite, which
    imports tawn.cli once at collection, before any test's TAWN_HOME is
    set)."""

    def _sync_domains(self) -> None:
        from typer.main import get_command as _get_command

        from tawn.domains.registry import enabled_domains

        for domain in enabled_domains():
            if domain.cli is not None and domain.name not in self.commands:
                click_command = _get_command(domain.cli)
                click_command.name = domain.name  # get_command() leaves this blank
                self.add_command(click_command, name=domain.name)

    def list_commands(self, ctx):
        self._sync_domains()
        return super().list_commands(ctx)

    def get_command(self, ctx, name):
        self._sync_domains()
        return super().get_command(ctx, name)


app = typer.Typer(
    help="Tawn — the twin you own.", invoke_without_command=True, cls=_DomainAwareGroup
)
grant_app = typer.Typer(no_args_is_help=True, help="Inspect and confirm capability grants.")
app.add_typer(grant_app, name="grant")
db_app = typer.Typer(no_args_is_help=True, help="Database bootstrap.")
app.add_typer(db_app, name="db")


@app.callback()
def main(ctx: typer.Context) -> None:
    """Bare `tawn` → chat with your twin. Use /help inside for slash commands."""
    if ctx.invoked_subcommand is not None:
        return
    # Bare tawn → go straight to chat (or setup if not initialized)
    home = tawn_home()
    if not (home / "raw").is_dir():
        from rich.console import Console
        from rich.padding import Padding

        import tawn
        from tawn.branding import banner

        console = Console()
        console.print(Padding(banner(tawn.__version__), (1, 0, 1, 1)))
        console.print("[yellow]not initialized[/] — run [bold]tawn init[/] or [bold]tawn setup[/] first")
        return
    ctx.invoke(chat, sensitive=False)


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


domain_app = typer.Typer(no_args_is_help=True, help="Domain plugins — pip-installed or local.")
app.add_typer(domain_app, name="domain")


@domain_app.command("list")
def domain_list() -> None:
    """Discovered domains, their source, and whether they're enabled."""
    from tawn.domains.registry import discovered_all

    for row in discovered_all(tawn_home()):
        mark = "enabled" if row["enabled"] else "disabled"
        typer.echo(f"{row['name']:<12} {row['source']:<20} {mark}")


@domain_app.command("enable")
def domain_enable(name: str) -> None:
    """Activate a discovered domain (pip package or local folder)."""
    from tawn.domains.registry import enable

    enable(name, tawn_home())
    typer.echo(f"{name}: enabled")


@domain_app.command("disable")
def domain_disable(name: str) -> None:
    """Deactivate a domain without uninstalling/deleting it."""
    from tawn.domains.registry import disable

    disable(name, tawn_home())
    typer.echo(f"{name}: disabled")


@domain_app.command("create")
def domain_create(name: str) -> None:
    """Describe a domain in plain English and Tawn builds it — or use the
    no-model field wizard if no provider is configured yet."""
    from rich.console import Console
    from rich.syntax import Syntax

    from tawn.domains.creation import (
        generate_domain_source,
        has_usable_model,
        write_local_domain,
    )
    from tawn.domains.registry import enable
    from tawn.model.router import default_router

    console = Console()
    home = tawn_home()

    if not has_usable_model(home):
        _domain_create_wizard(name, home, console)
        return

    router = default_router(home)
    description = typer.prompt(f"describe the '{name}' domain in plain English")
    while True:
        source = generate_domain_source(description, router)
        console.print(Syntax(source, "python", theme="ansi_dark"))
        choice = typer.prompt("[a]ccept / [r]egenerate (describe differently) / [c]ancel", default="a")
        if choice.lower().startswith("a"):
            path = write_local_domain(home, name, source)
            enable(name, home)
            typer.echo(f"{name} created at {path} and enabled")
            return
        if choice.lower().startswith("c"):
            typer.echo("cancelled — nothing written")
            return
        description = typer.prompt("describe it differently")


def _domain_create_wizard(name: str, home, console) -> None:
    """Path B: no model configured — declarative field wizard, targeting
    the same records engine work/research/academic/hobby are built on."""
    from tawn.domains.registry import enable

    console.print("[dim]no model configured — building this without one instead[/dim]")
    field_names: list[str] = []
    while True:
        fname = typer.prompt("field name (blank to finish)", default="")
        if not fname:
            break
        field_names.append(fname)
    if not field_names:
        typer.echo("no fields given — nothing created")
        return
    folder = home / "domains" / name
    folder.mkdir(parents=True, exist_ok=True)
    fields_repr = ", ".join(f"Field({fn!r})" for fn in field_names)
    domain_py = (
        "from tawn.domains.base import DomainSpec\n"
        "from tawn.domains.records import Collection, Field, record_domain\n\n"
        f"def register() -> DomainSpec:\n"
        f"    return record_domain(\n"
        f"        {name!r}, {name.title()!r},\n"
        f"        collections=[Collection(name={name!r}, label={name.title()!r}, "
        f"fields=[{fields_repr}])],\n"
        f"    )\n"
    )
    (folder / "domain.py").write_text(domain_py)
    enable(name, home)
    typer.echo(f"{name} created (field wizard) and enabled")


def _start_ngrok(port: int) -> str | None:
    """Start ngrok tunnel if ngrok is on PATH. Returns public HTTPS URL or None."""
    import json
    import shutil
    import subprocess
    import time
    import urllib.request
    import urllib.error

    if not shutil.which("ngrok"):
        return None
    try:
        # Check if ngrok is already running a tunnel for this port
        for _ in range(2):
            try:
                with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as r:
                    data = json.loads(r.read())
                for tunnel in data.get("tunnels", []):
                    if tunnel.get("proto") == "https":
                        return tunnel["public_url"]
            except (urllib.error.URLError, OSError):
                break

        subprocess.Popen(
            ["ngrok", "http", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # poll until tunnel appears (up to 10s)
        for i in range(20):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=3) as r:
                    data = json.loads(r.read())
                for tunnel in data.get("tunnels", []):
                    if tunnel.get("proto") == "https":
                        return tunnel["public_url"]
            except (urllib.error.URLError, OSError):
                continue
    except Exception:
        pass
    return None


def _ensure_hosts_entry() -> bool:
    """Add '127.0.0.1  tawn' to /etc/hosts if absent. Returns True when entry exists."""
    import socket
    import subprocess

    try:
        socket.gethostbyname("tawn")
        return True
    except OSError:
        pass

    ENTRY = "127.0.0.1  tawn  # tawn web\n"
    HOSTS = "/etc/hosts"
    try:
        if ENTRY.strip() in open(HOSTS).read():
            return False
        typer.echo("adding 'tawn' to /etc/hosts (sudo required once) …")
        result = subprocess.run(
            ["sudo", "tee", "-a", HOSTS],
            input=ENTRY.encode(),
            timeout=60,
            stdout=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except Exception:
        return False


def _web_pid_file(home: Path) -> Path:
    return home / "web.pid"


def _web_port_file(home: Path) -> Path:
    return home / "web.port"


def _web_is_running(home: Path) -> tuple[bool, int]:
    """Returns (is_running, pid). pid=0 if not running."""
    import os
    import signal

    pid_file = _web_pid_file(home)
    if not pid_file.exists():
        return False, 0
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIG_DFL)  # signal 0 = existence check
        return True, pid
    except (ValueError, ProcessLookupError, PermissionError):
        pid_file.unlink(missing_ok=True)
        return False, 0


web_app = typer.Typer(no_args_is_help=True, help="Web viewer daemon (start/stop/status).")
app.add_typer(web_app, name="web")


@web_app.command("start")
def web_start(port: int = typer.Option(8787, help="port on 127.0.0.1")) -> None:
    """Start the tawn web viewer in the background."""
    import os
    import sys
    import subprocess

    home = tawn_home()
    running, pid = _web_is_running(home)
    if running:
        saved_port = int(_web_port_file(home).read_text().strip()) if _web_port_file(home).exists() else port
        local_url = f"http://127.0.0.1:{saved_port}"
        typer.echo(f"already running (pid {pid})")
        typer.echo(f"local  → {local_url}")
        return

    host_ok = _ensure_hosts_entry()
    local_url = f"http://tawn:{port}" if host_ok else f"http://127.0.0.1:{port}"

    # spawn the internal _serve command as a detached subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "tawn._webserver", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    _web_pid_file(home).write_text(str(proc.pid))
    _web_port_file(home).write_text(str(port))

    typer.echo(f"tawn web started (pid {proc.pid})")
    typer.echo(f"local  → {local_url}")

    ngrok_url = _start_ngrok(port)
    if ngrok_url:
        typer.echo(f"public → {ngrok_url}")
    typer.echo("stop with: tawn web stop")


@web_app.command("stop")
def web_stop() -> None:
    """Stop the background web viewer."""
    import os
    import signal

    home = tawn_home()
    running, pid = _web_is_running(home)
    if not running:
        typer.echo("tawn web is not running")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        _web_pid_file(home).unlink(missing_ok=True)
        _web_port_file(home).unlink(missing_ok=True)
        typer.echo(f"stopped (pid {pid})")
    except ProcessLookupError:
        _web_pid_file(home).unlink(missing_ok=True)
        typer.echo("process already gone — cleaned up")


@web_app.command("status")
def web_status() -> None:
    """Show whether the web viewer is running and its URL."""
    home = tawn_home()
    running, pid = _web_is_running(home)
    if not running:
        typer.echo("stopped")
        return
    port = int(_web_port_file(home).read_text().strip()) if _web_port_file(home).exists() else 8787
    typer.echo(f"running  pid={pid}  local → http://127.0.0.1:{port}")


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
    from tawn.model.identity import with_baseline
    from tawn.model.router import default_router
    from tawn.model.types import Message

    home = tawn_home()
    router = default_router(home)
    msgs = with_baseline([Message(role="user", content=prompt)], home)
    tokens_in = tokens_out = 0
    error = None
    for chunk in router.stream(msgs, sensitive=sensitive):
        if chunk.error:
            error = chunk.error
            break
        typer.echo(chunk.text, nl=False)
        if chunk.done:
            tokens_in, tokens_out = chunk.tokens_in or 0, chunk.tokens_out or 0
    typer.echo()
    if error:
        typer.echo(f"model error: {error}", err=True)
        if "server_error" in error.lower() and not sensitive:
            typer.echo("is ollama running?  ollama serve", err=True)
        raise typer.Exit(1)
    typer.echo(
        f"\n[tokens {tokens_in}→{tokens_out}{' · sensitive/local' if sensitive else ''}]",
        err=True,
    )


_SLASH_HELP = """[bold]slash commands[/bold]
  /new · /clear          clear conversation history
  /model [target]        switch model (or picker if no arg)
  /status                system health check
  /grants                show capability grants
  /ledger                sovereignty ledger (last 10 calls)
  /domain list           enabled + discovered domains
  /domain create <name>  create a new domain
  /web                   open web viewer (starts tawn web in background)
  /profile               show or edit your personality profile
  /note <text>           save a note to memory
  /recall <query>        search compiled memory
  /help                  this message
  exit · quit · ctrl-d   leave chat"""


def _chat_slash_status(console, home) -> None:
    from tawn.capability.grants import load_verified
    from tawn.capability.integrity import IntegrityError
    from tawn.dbsetup import probe
    from tawn.model.router import default_router

    initialized = (home / "raw").is_dir()
    grants_ok = True
    try:
        g = load_verified(home / "grants.yaml") if (home / "grants.yaml").exists() else None
        grants_detail = f"{len(g.read)}r {len(g.write)}w" if g else "deny-all"
    except IntegrityError:
        grants_ok = False
        grants_detail = "EDITED — run `tawn grant confirm`"
    db_ok = probe(settings().db_url).can_connect
    try:
        router = default_router(home)
        providers = " → ".join(p.name for p in router.providers)
    except Exception:
        providers = "none"
    mark = lambda ok: "[green]✓[/]" if ok else "[red]✗[/]"
    console.print(f"  {mark(initialized)} home      {home}")
    console.print(f"  {mark(grants_ok)} grants    {grants_detail}")
    console.print(f"  {mark(db_ok)} database  {'connected' if db_ok else 'unreachable'}")
    console.print(f"  [dim]models:[/dim] {providers}")


def _chat_slash_grants(console, home) -> None:
    try:
        g = load_verified(home / "grants.yaml")
        console.print(f"  read:    {g.read or '(none)'}")
        console.print(f"  write:   {g.write or '(none)'}")
        console.print(f"  system:  {'on' if g.system else 'off'}")
    except IntegrityError:
        console.print("[red]grants.yaml edited — run `tawn grant confirm`[/]")
    except FileNotFoundError:
        console.print("[dim]no grants.yaml — run `tawn init`[/dim]")


def _chat_slash_ledger(console, home) -> None:
    from tawn.model.ledger import Ledger

    entries = Ledger(home / "ledger.jsonl").entries()
    if not entries:
        console.print("[dim]ledger empty[/dim]")
        return
    for e in entries[-10:]:
        ts = e["ts"][:16].replace("T", " ")
        console.print(f"  {ts}  {e['provider']}/{e['model']}  {e['tokens_in']}→{e['tokens_out']}tok  ok={e['ok']}")


def _chat_slash_domain(console, home, arg: str) -> None:
    from tawn.domains.registry import discovered_all

    if not arg or arg == "list":
        for row in discovered_all(home):
            mark = "[green]on[/]" if row["enabled"] else "[dim]off[/]"
            console.print(f"  {mark}  {row['name']:<14} {row['source']}")
        return
    if arg.startswith("create"):
        name = arg[len("create"):].strip()
        if not name:
            name = console.input("[dim]domain name:[/] ").strip()
        if name:
            ctx = typer.Context(typer.main.get_command(app))
            domain_create(name)
        return
    console.print(f"[dim]unknown: /domain {arg}  (try list or create <name>)[/dim]")


def _chat_slash_web(console, home, port: int) -> None:
    import subprocess
    import sys

    console.print(f"[dim]starting tawn web on port {port} in background …[/dim]")
    subprocess.Popen(
        [sys.executable, "-m", "tawn", "web", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    console.print(f"[dim]open http://127.0.0.1:{port}[/dim]")


def _chat_slash_profile(console, home) -> None:
    from tawn.model.personality import ONBOARDING_QUESTIONS, load_profile, save_profile

    profile = load_profile(home)
    if not any(profile.values()):
        console.print("[dim]no profile yet — answering these updates it:[/dim]")
    else:
        console.print("[dim]current profile (enter to keep, type to change):[/dim]")
    for key, question in ONBOARDING_QUESTIONS:
        current = profile.get(key, "")
        prompt = f"  {question}" + (f" [{current}]" if current else "")
        try:
            answer = console.input(prompt + " ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if answer or not current:
            profile[key] = answer
    save_profile(home, profile)
    console.print("[dim]profile saved[/dim]")


def _run_onboarding(console, home) -> None:
    """First-run personality collection — asked once, stored, never again unless /profile."""
    from tawn.model.personality import ONBOARDING_QUESTIONS, save_profile

    console.print(
        "\n[bold]Hi — I'm Tawn, your personal digital twin.[/bold]\n"
        "A few quick questions to get started (press Enter to skip any):\n"
    )
    profile: dict = {}
    for key, question in ONBOARDING_QUESTIONS:
        try:
            answer = console.input(f"  {question} ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if answer:
            profile[key] = answer
    save_profile(home, profile)
    name = profile.get("name", "")
    console.print(
        f"\n[dim]{'Nice to meet you, ' + name + '.' if name else 'Got it.'} "
        "Your profile is saved — update it anytime with /profile.[/dim]\n"
    )


@app.command()
def chat(
    sensitive: bool = typer.Option(
        False, "--sensitive", help="whole session never leaves this machine"
    ),
) -> None:
    """Talk to your twin — history carries across turns. exit/quit to leave."""
    from rich.console import Console

    from tawn.model.identity import with_baseline
    from tawn.model.personality import profile_is_empty
    from tawn.model.router import default_router
    from tawn.model.types import Message

    from tawn.history import Session as HistorySession

    home = tawn_home()
    console = Console()
    router = default_router(home)
    names = " → ".join(p.name for p in router.providers)
    session = HistorySession(home)

    # First-run personality onboarding
    if profile_is_empty(home):
        _run_onboarding(console, home)

    console.print(
        f"[dim]tawn · {names}"
        f"{' · sensitive' if sensitive else ''}"
        " · /help for commands · exit to leave[/dim]"
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
        low = line.lower()

        # ── Slash commands ────────────────────────────────────────────────────
        if low in ("exit", "quit", "/exit", "/quit"):
            break
        if low in ("/new", "/clear"):
            history.clear()
            console.print("[dim]history cleared[/dim]")
            continue
        if low in ("/help", "/?"):
            console.print(_SLASH_HELP)
            continue
        if low in ("/status", "/doctor"):
            _chat_slash_status(console, home)
            continue
        if low in ("/grants",):
            _chat_slash_grants(console, home)
            continue
        if low in ("/ledger",):
            _chat_slash_ledger(console, home)
            continue
        if low.startswith("/domain"):
            _chat_slash_domain(console, home, low[len("/domain"):].strip())
            continue
        if low.startswith("/web"):
            arg = low[len("/web"):].strip()
            port = int(arg) if arg.isdigit() else 8787
            _chat_slash_web(console, home, port)
            continue
        if low in ("/profile",):
            _chat_slash_profile(console, home)
            # Rebuild router so new profile lands in baseline immediately
            continue
        if low.startswith("/model"):
            arg = line[len("/model"):].strip()
            target = arg or _pick_model_target()
            if target:
                _set_config("model", target)
                router = default_router(home)
                console.print(f"[dim]model set to {target}[/dim]")
            continue
        if low.startswith("/note"):
            text = line[len("/note"):].strip()
            if text:
                result = note(text, home=home)
                console.print(f"[dim]noted → {result['path']}[/dim]")
            else:
                console.print("[dim]/note <text>[/dim]")
            continue
        if low.startswith("/recall"):
            query = line[len("/recall"):].strip()
            if query:
                from sqlalchemy.orm import Session as SASession
                with SASession(make_engine()) as _s:
                    _result = recall(query=query, home=home, session=_s, top_k=5)
                _chunks = _result.get("chunks", [])
                if _chunks:
                    for _c in _chunks:
                        console.print(f"[dim][{_c['source']}][/dim]")
                        console.print(_c["content"][:300])
                else:
                    console.print("[dim]no results[/dim]")
            else:
                console.print("[dim]/recall <query>[/dim]")
            continue
        if low.startswith("/"):
            console.print(f"[dim]unknown command — try /help[/dim]")
            continue

        # ── Normal message ────────────────────────────────────────────────────
        history.append(Message(role="user", content=line))
        session.append("user", line)
        msgs = with_baseline(history, home)
        parts: list[str] = []
        error: str | None = None
        tokens_in = tokens_out = 0
        model_used = names
        for chunk in router.stream(msgs, sensitive=sensitive):
            if chunk.error:
                error = chunk.error
                break
            console.print(chunk.text, end="", highlight=False)
            parts.append(chunk.text)
            if chunk.done:
                tokens_in, tokens_out = chunk.tokens_in or 0, chunk.tokens_out or 0
        console.print()
        if error:
            history.pop()
            console.print(f"[red]model error:[/] {error}")
            if "not found" in error.lower() or "pull" in error.lower():
                console.print("[dim]hint: no local model — run `tawn model setup`[/dim]")
            elif "connect" in error.lower():
                console.print("[dim]hint: is ollama running?  ollama serve[/dim]")
            continue
        full_text = "".join(parts)
        history.append(Message(role="assistant", content=full_text))
        session.append("assistant", full_text, model=model_used, tokens_in=tokens_in, tokens_out=tokens_out)
        console.print(
            f"[dim][{tokens_in}→{tokens_out} tok{' · local' if sensitive else ''}][/dim]"
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

    domains_path = home / "domains.yaml"
    if not domains_path.exists():
        import yaml as _yaml

        domains_path.write_text(
            _yaml.safe_dump(
                {"enabled": ["wealth", "work", "research", "academic", "hobby"]},
                sort_keys=True,
            )
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


# ── memory commands (top-level) ────────────────────────────────────────────────

@app.command("note")
def cmd_note(
    payload: str = typer.Argument(..., help="Text to record"),
    domain: str = typer.Option(None, "--domain", "-d", help="Domain tag"),
    type: str = typer.Option("note", "--type", "-t", help="Entry type (note/fact/task/…)"),
    confidence: str = typer.Option("medium", "--confidence", "-c", help="high/medium/low"),
    ttl_days: int = typer.Option(None, "--ttl", help="Days until expiry (omit = forever)"),
) -> None:
    """Write a timestamped note to memory (queues a background compile)."""
    home = tawn_home()
    result = note(
        payload,
        domain=domain or None,
        type=type,
        confidence=confidence,
        ttl_days=ttl_days,
        home=home,
    )
    typer.echo(f"noted → {result['path']}")


@app.command("recall")
def cmd_recall(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n"),
    domain: str = typer.Option(None, "--domain", "-d"),
    compose: bool = typer.Option(False, "--compose", help="Synthesise answer with LLM"),
) -> None:
    """Search compiled memory for relevant chunks."""
    from sqlalchemy.orm import Session as SASession

    home = tawn_home()
    engine = make_engine()
    fmt = "composed" if compose else "snippets"
    with SASession(engine) as s:
        result = recall(query=query, home=home, session=s, top_k=limit, domain=domain or None, format=fmt)

    if fmt == "composed":
        typer.echo(result.get("answer", "") or "(no results)")
        return
    chunks = result.get("chunks", [])
    if not chunks:
        typer.echo("no results")
        return
    for c in chunks:
        typer.echo(f"\n[{c['source']}]")
        typer.echo(c["content"][:400])


@app.command("brief")
def cmd_brief(
    domain: str = typer.Argument("*", help="Domain name, or '*' for all"),
) -> None:
    """Print a domain knowledge summary."""
    from sqlalchemy.orm import Session as SASession

    home = tawn_home()
    engine = make_engine()
    with SASession(engine) as s:
        d = brief(domain=domain, home=home, session=s)
    typer.echo(f"domain    : {d['domain']}")
    typer.echo(f"chunks    : {d['chunk_count']}")
    typer.echo(f"entities  : {d['entity_count']}")
    if d.get("stale_chunk_count"):
        typer.echo(f"stale     : {d['stale_chunk_count']}")
    if d.get("last_compiled"):
        typer.echo(f"compiled  : {d['last_compiled']}")
    typer.echo(f"\n{d['summary']}")


@app.command("compile")
def cmd_compile(
    rebuild: bool = typer.Option(False, "--rebuild", help="Force re-process all files"),
    status: bool = typer.Option(False, "--status", help="Show status only (no compile)"),
    schedule: bool = typer.Option(False, "--schedule", help="Install systemd user timer"),
) -> None:
    """Compile raw/ into searchable chunks + wiki. Use --status to check queue."""
    if schedule:
        _install_compile_timer()
        return

    from sqlalchemy.orm import Session as SASession

    home = tawn_home()
    engine = make_engine()

    if status:
        with SASession(engine) as s:
            info = compile_status(home, s)
        typer.echo(f"pending  : {info['pending']}")
        typer.echo(f"last run : {info.get('last_compiled') or 'never'}")
        return

    with SASession(engine) as s:
        result = run_compile(home, s, rebuild=rebuild)
        s.commit()
    mark = "ok" if result.ok else "failed"
    typer.echo(
        f"compile {mark} — {result.files_processed} files, "
        f"+{result.chunks_added}/-{result.chunks_removed} chunks, "
        f"{result.entities_resolved} entities"
    )


def _install_compile_timer() -> None:
    """Write a systemd user timer that runs `tawn compile` every 5 minutes."""
    import sys
    systemd_dir = Path.home() / ".config" / "systemd" / "user"
    systemd_dir.mkdir(parents=True, exist_ok=True)
    exe = sys.executable
    service = (
        "[Unit]\nDescription=Tawn memory compiler\n\n"
        "[Service]\nType=oneshot\n"
        f"ExecStart={exe} -m tawn compile\n"
    )
    timer = (
        "[Unit]\nDescription=Tawn memory compiler timer\n\n"
        "[Timer]\nOnBootSec=2min\nOnUnitActiveSec=5min\n\n"
        "[Install]\nWantedBy=timers.target\n"
    )
    (systemd_dir / "tawn-compile.service").write_text(service)
    (systemd_dir / "tawn-compile.timer").write_text(timer)
    typer.echo(f"wrote systemd units to {systemd_dir}")
    typer.echo("enable:  systemctl --user enable --now tawn-compile.timer")


# ── mcp command ────────────────────────────────────────────────────────────────

@app.command("mcp")
def mcp_serve() -> None:
    """Start the Tawn MCP server (stdio transport)."""
    from tawn.mcp_server import mcp
    mcp.run(transport="stdio")
