"""`tawn domain create` — Path A (LLM-assisted) generation logic and the
local-domain write step shared by both paths (LLM and field wizard)."""

from pathlib import Path

from tawn.model.router import Router, usable_models
from tawn.model.types import Message

GENERATION_PROMPT = """You generate a Tawn domain module. Output ONLY the
contents of a Python file — no markdown fences, no commentary.

Contract (must match exactly):
    from tawn.domains.base import DomainSpec

    def register() -> DomainSpec:
        ...  # cli: typer.Typer | None, api_router: fastapi.APIRouter | None

The view endpoint on api_router, if present, must return:
    {{"title": str, "stat": {{"label", "value", "sublabel"}}?, "sections": [...]}}
where each section is {{"type": "table", "columns": [...], "rows": [[...]]}},
{{"type": "list", "items": [{{"label", "value"?}}]}}, or
{{"type": "empty", "message": str}}.

Reference example (the wealth domain, for shape only):
    from tawn.domains.base import DomainSpec
    def register() -> DomainSpec:
        import typer
        from fastapi import APIRouter
        app = typer.Typer()
        router = APIRouter()

        @router.get("/view")
        def view():
            return {{"title": "Example", "sections": [{{"type": "empty", "message": "no data yet"}}]}}

        return DomainSpec(name="example", label="Example", cli=app, api_router=router)

User's description of the domain they want:
{description}
"""


def generate_domain_source(description: str, router: Router) -> str:
    prompt = GENERATION_PROMPT.format(description=description)
    resp = router.complete([Message(role="user", content=prompt)])
    return resp.text.strip()


def write_local_domain(home: Path, name: str, source: str) -> Path:
    folder = home / "domains" / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "domain.py"
    path.write_text(source)
    return path


def has_usable_model(home: Path) -> bool:
    """Same check `tawn ask` would fail on — is there any provider that
    could actually answer right now? Reuses the same keyed-cloud +
    installed-local-model check the `tawn model use` picker is built on."""
    return bool(usable_models(home))
