"""Multi-collection record-keeping engine — the shared foundation behind
work/research/academic/hobby (and the `tawn domain create` field-wizard
fallback, which is the single-collection case of this same engine).

Each domain is one or more named collections (e.g. work = projects +
tasks). Every collection gets its own `add`/`list` CLI subcommand pair
and its own JSONL file under ~/.tawn/domains/<domain>/<collection>.jsonl.
The view endpoint renders one table section per collection — the exact
Domain View Protocol schema every domain speaks, no special-casing needed
in the frontend.
"""

import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path

import typer
from fastapi import APIRouter

from tawn.domains.base import DomainSpec
from tawn.home import tawn_home


@dataclass
class Field:  # noqa: A001 — matches the domain vocabulary (fields.yaml), not the builtin
    name: str
    type: str = "text"  # text | number | date | bool


@dataclass
class Collection:
    name: str
    label: str
    fields: list[Field] = field(default_factory=list)


def _storage_path(home: Path, domain_name: str, collection_name: str) -> Path:
    return home / "domains" / domain_name / f"{collection_name}.jsonl"


def _read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _build_collection_cli(domain_name: str, collection: Collection, home: Path | None) -> typer.Typer:
    app = typer.Typer(help=f"{collection.label} records")
    field_names = [f.name for f in collection.fields]

    def _add_impl(**values: str) -> None:
        h = home or tawn_home()
        record = {name: values[name] for name in field_names}
        path = _storage_path(h, domain_name, collection.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(record) + "\n")
        typer.echo(f"added: {record}")

    params = [
        inspect.Parameter(
            fname,
            inspect.Parameter.KEYWORD_ONLY,
            default=typer.Option(..., f"--{fname.replace('_', '-')}"),
            annotation=str,
        )
        for fname in field_names
    ]
    _add_impl.__signature__ = inspect.Signature(params)
    app.command("add")(_add_impl)

    @app.command("list")
    def _list_impl() -> None:
        h = home or tawn_home()
        records = _read_records(_storage_path(h, domain_name, collection.name))
        if not records:
            typer.echo("no records yet")
            return
        for r in records:
            typer.echo(", ".join(f"{k}={v}" for k, v in r.items()))

    return app


def record_domain(name: str, label: str, collections: list[Collection], home: Path | None = None) -> DomainSpec:
    app = typer.Typer(help=f"{label} domain")

    @app.callback()
    def _cb() -> None:
        pass

    for collection in collections:
        app.add_typer(_build_collection_cli(name, collection, home), name=collection.name)

    router = APIRouter()

    @router.get("/view")
    def view():
        sections = []
        for collection in collections:
            h = home or tawn_home()
            records = _read_records(_storage_path(h, name, collection.name))
            columns = [f.name for f in collection.fields]
            if not records:
                sections.append({"type": "empty", "message": f"no {collection.label.lower()} yet"})
            else:
                rows = [[r.get(c, "") for c in columns] for r in records]
                sections.append({"type": "table", "columns": columns, "rows": rows})
        return {"title": label, "sections": sections}

    return DomainSpec(name=name, label=label, cli=app, api_router=router, nav=True)
