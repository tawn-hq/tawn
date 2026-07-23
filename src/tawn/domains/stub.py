"""Factory for domains that are registered but not yet built out (work,
research, academic, hobby — real logic is Stage 12 scope). Proves the
plugin contract with concrete built-in examples without writing four
domains' worth of business logic."""

import typer
from fastapi import APIRouter

from tawn.domains.base import DomainSpec


def make_stub_domain(name: str, label: str) -> DomainSpec:
    app = typer.Typer(help=f"{label} domain (not yet implemented)")

    @app.callback()
    def _cb() -> None:
        pass

    @app.command()
    def status() -> None:
        typer.echo(f"{label}: not yet implemented — tracked at Stage 12")

    router = APIRouter()

    @router.get("/view")
    def view():
        return {
            "title": label,
            "sections": [{"type": "empty", "message": "not yet implemented — tracked at Stage 12"}],
        }

    return DomainSpec(name=name, label=label, cli=app, api_router=router, nav=True)
