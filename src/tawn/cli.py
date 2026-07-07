"""tawn CLI (Typer). Stage 0 surface: init, grant list, grant confirm."""

import typer

from tawn.capability.audit import AuditLog
from tawn.capability.grants import DEFAULT_GRANTS_YAML, load_verified
from tawn.capability.integrity import IntegrityError
from tawn.capability.integrity import confirm as integrity_confirm
from tawn.home import init_home, tawn_home

app = typer.Typer(no_args_is_help=True, help="Tawn — the twin you own.")
grant_app = typer.Typer(no_args_is_help=True, help="Inspect and confirm capability grants.")
app.add_typer(grant_app, name="grant")


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
