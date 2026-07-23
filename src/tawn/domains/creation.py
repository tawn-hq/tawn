"""`tawn domain create` — Path A (LLM-assisted) generation logic and the
local-domain write step shared by both paths (LLM and field wizard)."""

from pathlib import Path

from tawn.model.router import Router, usable_models
from tawn.model.types import Message

GENERATION_PROMPT = """You generate a Tawn domain module. Output ONLY a valid Python file — no markdown fences, no commentary, no explanation.

## Strict rules
- ONLY import from: standard library, typer, fastapi, pydantic, pathlib, yaml, json, rich, tawn.domains.base
- NEVER import from tawn.lib, tawn.store, tawn.model, tawn.db, or any other tawn internal
- Persist data using plain YAML or JSON files under pathlib.Path.home() / ".tawn" / "domains" / "<name>"
- The file MUST define exactly one function: `def register() -> DomainSpec`

## Data persistence pattern (use this exactly)
    import json
    from pathlib import Path

    _DATA_PATH = Path.home() / ".tawn" / "domains" / "<domain-name>" / "data.json"

    def _load() -> dict:
        if not _DATA_PATH.exists():
            return {{}}
        return json.loads(_DATA_PATH.read_text())

    def _save(data: dict) -> None:
        _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DATA_PATH.write_text(json.dumps(data, indent=2))

## View endpoint response shape
    {{
        "title": str,
        "stat": {{"label": str, "value": str, "sublabel": str}},   # optional
        "sections": [
            {{"type": "table", "columns": ["Col1", "Col2"], "rows": [["a", "b"]]}},
            {{"type": "list", "items": [{{"label": "key", "value": "val"}}]}},
            {{"type": "empty", "message": "No data yet."}}
        ]
    }}

## Minimal working example
    from tawn.domains.base import DomainSpec
    import json, typer
    from pathlib import Path
    from fastapi import APIRouter

    _DATA = Path.home() / ".tawn" / "domains" / "example" / "data.json"

    def _load():
        return json.loads(_DATA.read_text()) if _DATA.exists() else []

    def _save(items):
        _DATA.parent.mkdir(parents=True, exist_ok=True)
        _DATA.write_text(json.dumps(items))

    def register() -> DomainSpec:
        cli = typer.Typer(help="Manage example items.")
        api = APIRouter()

        @cli.command("add")
        def add(name: str):
            items = _load(); items.append(name); _save(items)
            typer.echo(f"Added {{name}}")

        @api.get("/view")
        def view():
            items = _load()
            if not items:
                return {{"title": "Example", "sections": [{{"type": "empty", "message": "No items yet."}}]}}
            return {{
                "title": "Example",
                "sections": [{{"type": "list", "items": [{{"label": i}} for i in items]}}]
            }}

        return DomainSpec(name="example", label="Example", cli=cli, api_router=api)

Now generate the domain the user requested. Replace "example" with the correct domain name throughout.

User's description:
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
