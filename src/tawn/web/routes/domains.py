"""Web-based domain creation — draft/promote/discard with live preview."""

import shutil

from fastapi import APIRouter
from pydantic import BaseModel

from tawn.domains.creation import generate_domain_source, has_usable_model
from tawn.domains.registry import _load_local_domain, enable, disable
from tawn.home import tawn_home

router = APIRouter()


def _draft_dir(home, name):
    return home / "domains" / ".drafts" / name


class DraftBody(BaseModel):
    name: str
    description: str


@router.post("/draft")
def draft(body: DraftBody):
    home = tawn_home()
    if not has_usable_model(home):
        return {"needs_wizard": True}

    from tawn.model.router import default_router

    source = generate_domain_source(body.description, default_router(home))
    folder = _draft_dir(home, body.name)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "domain.py").write_text(source)

    view = None
    error = None
    spec = _load_local_domain(folder)
    if spec is None:
        error = "generated domain.py failed to import"
    elif spec.api_router is None:
        error = "generated domain has no api_router / view endpoint"
    else:
        try:
            view_fn = next(r.endpoint for r in spec.api_router.routes if r.path == "/view")
            view = view_fn()
        except Exception as exc:
            error = f"view() raised: {exc}"

    return {"source": source, "view": view, "error": error}


@router.post("/draft/{name}/promote")
def promote(name: str):
    home = tawn_home()
    draft_folder = _draft_dir(home, name)
    real_folder = home / "domains" / name
    real_folder.parent.mkdir(parents=True, exist_ok=True)
    if real_folder.exists():
        shutil.rmtree(real_folder)
    shutil.move(str(draft_folder), str(real_folder))
    enable(name, home)
    return {"ok": True}


@router.post("/{name}/enable")
def enable_domain(name: str):
    enable(name, tawn_home())
    return {"ok": True}


@router.delete("/{name}/enable")
def disable_domain(name: str):
    disable(name, tawn_home())
    return {"ok": True}


@router.delete("/draft/{name}")
def discard(name: str):
    home = tawn_home()
    folder = _draft_dir(home, name)
    if folder.exists():
        shutil.rmtree(folder)
    return {"ok": True}
