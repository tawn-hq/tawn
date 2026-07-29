"""Tawn web viewer — JSON API only (design spec: web-viewer-v2).

React SPA in frontend/dist is served as static files with SPA fallback;
every domain's api_router (if any) mounts at /api/<name>.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from tawn.domains.registry import enabled_domains
from tawn.home import tawn_home

# In-package dist (pip/pipx install). Falls back to repo-root location for
# editable installs that haven't run setup.py (plain `pip install -e .`).
_pkg_dist = Path(__file__).parent / "dist"
_dev_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
FRONTEND_DIST = _pkg_dist if _pkg_dist.is_dir() else _dev_dist


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="tawn", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")

    @app.get("/api/docs", response_class=HTMLResponse, include_in_schema=False)
    def api_docs():
        # Scalar reads the same OpenAPI schema FastAPI already generates —
        # no new Python dependency, just a CDN-loaded UI. Registered here
        # (ahead of the SPA catch-all mounted at the bottom of this
        # function) so it isn't swallowed by client-side routing.
        return (
            "<!doctype html><html><head><title>tawn API</title>"
            '<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>'
            "</head><body>"
            '<script id="api-reference" data-url="/api/openapi.json"></script>'
            '<script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>'
            "</body></html>"
        )

    @app.get("/api/status")
    def status():
        from tawn.staleness import staleness_report

        home = tawn_home()
        # Surfaced here so a browser session can tell it is talking to a
        # daemon older than the code on disk, rather than concluding a fix
        # did not work.
        return {
            "initialized": (home / "raw").is_dir(),
            "code": staleness_report(home, "web"),
        }

    @app.get("/api/domains")
    def domains():
        from tawn.domains.registry import discovered_all, enabled_names
        home = tawn_home()
        enabled = enabled_names(home)
        all_domains = discovered_all(home)
        # Build label/nav from spec for enabled ones; stub for disabled
        enabled_specs = {s.name: s for s in enabled_domains(home=home)}
        out = []
        for row in all_domains:
            name = row["name"]
            spec = enabled_specs.get(name)
            out.append({
                "name": name,
                "label": spec.label if spec else name.capitalize(),
                "nav": name in enabled,
            })
        return out

    from tawn.web.routes.setup import router as setup_router
    from tawn.web.routes.chat import router as chat_router
    from tawn.web.routes.grants import router as grants_router
    from tawn.web.routes.domains import router as domain_create_router
    from tawn.web.routes.profile import router as profile_router
    from tawn.web.routes.history import router as history_router
    from tawn.web.routes.memory import router as memory_router
    from tawn.web.routes.federation import router as federation_router
    from tawn.web.routes.update import router as update_router
    from tawn.web.routes.wiki import router as wiki_router
    from tawn.web.routes.observability import router as observability_router
    from tawn.web.routes.observer import router as observer_router
    from tawn.web.routes.tools import router as tools_router

    app.include_router(setup_router, prefix="/api/setup")
    app.include_router(chat_router, prefix="/api/chat")
    app.include_router(grants_router, prefix="/api")
    app.include_router(domain_create_router, prefix="/api/domains")
    app.include_router(profile_router, prefix="/api")
    app.include_router(history_router, prefix="/api")
    app.include_router(memory_router, prefix="/api")
    app.include_router(federation_router, prefix="/api/federation")
    app.include_router(update_router, prefix="/api/update")
    # Mounted ahead of the SPA catch-all at the bottom of this function,
    # or client-side routing swallows it.
    app.include_router(wiki_router, prefix="/api/wiki")
    app.include_router(observability_router, prefix="/api/observability")
    app.include_router(observer_router, prefix="/api/observer")
    app.include_router(tools_router, prefix="/api/tools")

    from fastapi import Depends as _Depends
    from sqlalchemy.orm import Session as _Session
    from tawn.db import get_session as _get_session

    @app.get("/api/export", tags=["export"])
    async def api_export(
        format: str = "both",
        session: _Session = _Depends(_get_session),
    ):
        from tawn.federation.exporter import export as _do_export
        return _do_export(tawn_home(), session, fmt=format)

    @app.get("/api/export/download", tags=["export"])
    async def api_export_download(
        format: str = "jsonl",
        session: _Session = _Depends(_get_session),
    ):
        """Stream export as a direct file download."""
        import io as _io
        import zipfile as _zipfile
        import datetime as _dt
        from fastapi.responses import StreamingResponse as _SR
        from tawn.memory.schema import Chunk as _Chunk, Entity as _Entity
        from tawn.federation.exporter import _export_jsonl as _xjsonl
        import json as _json

        today = _dt.date.today().strftime("%Y-%m-%d")
        chunks = session.query(_Chunk).all()
        entities = session.query(_Entity).all()

        if format == "jsonl":
            from collections import defaultdict as _dd
            entity_by_domain: dict = _dd(list)
            for e in entities:
                if e.domain:
                    entity_by_domain[e.domain].append(e.canonical)
            lines = []
            for c in chunks:
                lines.append(_json.dumps({
                    "id": c.id, "domain": c.domain, "content": c.content,
                    "source": c.source_path,
                    "entities": entity_by_domain.get(c.domain or "", []),
                    "compiled_at": c.compiled_at.isoformat() if c.compiled_at else None,
                    "stale": c.stale,
                }))
            content = "\n".join(lines)
            return _SR(
                iter([content.encode()]),
                media_type="application/x-ndjson",
                headers={"Content-Disposition": f"attachment; filename=tawn-export-{today}.jsonl"},
            )

        # zip: run export to disk then zip the output dir
        from tawn.federation.exporter import export as _do_export
        result = _do_export(tawn_home(), session, fmt="both")
        out_dir = _Path(result["out"])
        buf = _io.BytesIO()
        with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
            for fpath in out_dir.rglob("*"):
                if fpath.is_file():
                    zf.write(fpath, fpath.relative_to(out_dir))
        buf.seek(0)
        return _SR(
            iter([buf.read()]),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=tawn-export-{today}.zip"},
        )

    @app.get("/api/models")
    def all_models():
        from tawn.model.router import usable_models
        return usable_models(tawn_home())

    @app.get("/api/models/embed")
    def get_embed_model():
        from tawn.compiler.embedder import get_embed_config, _OLLAMA_MODELS, _OPENAI_MODEL, _GEMINI_MODEL
        model, dims = get_embed_config(tawn_home())
        candidates = [
            *[{"id": m, "dims": d, "provider": "ollama", "label": m} for m, d in _OLLAMA_MODELS],
            {"id": _OPENAI_MODEL, "dims": 1536, "provider": "openai", "label": _OPENAI_MODEL},
            {"id": _GEMINI_MODEL, "dims": 768, "provider": "gemini", "label": _GEMINI_MODEL},
        ]
        return {"current": model, "dims": dims, "candidates": candidates}

    class EmbedModelBody(BaseModel):
        model: str

    @app.put("/api/models/embed")
    def set_embed_model(body: EmbedModelBody, force: bool = False):
        """Switch the embedding model.

        Refuses when the corpus already holds vectors of a different width:
        distance operators reject mixed-width comparisons, so accepting the
        change would silently break recall until a rebuild. Previously this
        wrote the new dims and left compile dying on
        `expected 768 dimensions, not 1536`.
        """
        from tawn.compiler.embedder import _chain, _write_config
        from tawn.memory.schema import Chunk

        for model_name, dims, fn in _chain():
            if model_name != body.model:
                continue
            try:
                vec = fn("test")
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

            new_dims = len(vec)
            if not force:
                from tawn.db import make_engine
                from sqlalchemy.orm import Session as _S

                try:
                    with _S(make_engine()) as s:
                        existing = (
                            s.query(Chunk)
                            .filter(Chunk.embedding.isnot(None))
                            .count()
                        )
                except Exception:
                    existing = 0

                current_dims = get_embed_model().get("dims") or 0
                if existing and current_dims and current_dims != new_dims:
                    return {
                        "ok": False,
                        "needs_rebuild": True,
                        "error": (
                            f"{existing} chunks are embedded at {current_dims} dimensions; "
                            f"{model_name} produces {new_dims}. Run `tawn compile --rebuild` "
                            f"to re-embed, or repeat with force=true to switch now and "
                            f"leave recall broken until you do."
                        ),
                    }

            _write_config(tawn_home(), {"embed_model": model_name, "embed_dims": new_dims})
            return {"ok": True, "model": model_name, "dims": new_dims}
        return {"ok": False, "error": f"unknown model: {body.model}"}

    @app.get("/api/browse/folder")
    def browse_folder():
        """Open a native OS folder picker and return the selected path."""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes("-topmost", True)
            path = filedialog.askdirectory(title="Select folder")
            root.destroy()
            return {"path": path or None}
        except Exception as exc:
            return {"path": None, "error": str(exc)}

    @app.get("/api/logs")
    def get_logs(n: int = 200):
        log_path = tawn_home() / "web.log"
        if not log_path.exists():
            return {"lines": [], "total": 0}
        all_lines = log_path.read_text(errors="replace").splitlines()
        tail = all_lines[-n:] if len(all_lines) > n else all_lines
        return {"lines": tail, "total": len(all_lines)}

    # ── Config routes ──────────────────────────────────────────────────────────
    from tawn.user_config import (
        all_keys as _cfg_keys, load_user_config as _load_cfg,
        set_config_value as _set_cfg, reset_config_value as _reset_cfg,
    )
    from pydantic import BaseModel as _BM

    class _ConfigPatch(_BM):
        key: str
        value: str

    @app.get("/api/config")
    def get_config():
        return _load_cfg(tawn_home())

    @app.patch("/api/config")
    def patch_config(body: _ConfigPatch):
        home = tawn_home()
        try:
            coerced = _set_cfg(home, body.key, body.value)
            return {"ok": True, "key": body.key, "value": coerced}
        except (KeyError, ValueError) as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=str(e))

    @app.delete("/api/config/{key}")
    def reset_config(key: str):
        home = tawn_home()
        try:
            val = _reset_cfg(home, key)
            return {"ok": True, "key": key, "value": val}
        except KeyError as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=str(e))

    # ── Audit routes ────────────────────────────────────────────────────────────
    from tawn.capability.audit import AuditLog as _AuditLog
    from fastapi.responses import Response as _Response

    def _audit_log() -> _AuditLog:
        return _AuditLog(tawn_home() / "audit.jsonl")

    @app.get("/api/audit", operation_id="get_audit_log")
    def get_audit(limit: int = 100, offset: int = 0):
        log = _audit_log()
        all_entries = log.entries()
        total = len(all_entries)
        page = all_entries[offset: offset + limit]
        return {"total": total, "entries": page}

    @app.get("/api/audit/verify")
    def audit_verify():
        return _audit_log().verify_chain()

    @app.get("/api/audit/export")
    def audit_export(format: str = "json"):
        log = _audit_log()
        if format == "csv":
            return _Response(content=log.export_csv(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=tawn-audit.csv"})
        return _Response(content=log.export_json(), media_type="application/json",
                         headers={"Content-Disposition": "attachment; filename=tawn-audit.json"})

    for domain in enabled_domains(home=tawn_home()):
        if domain.api_router is not None:
            app.include_router(domain.api_router, prefix=f"/api/{domain.name}")

    if FRONTEND_DIST.is_dir():
        if (FRONTEND_DIST / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/favicon.svg")
        def favicon():
            return FileResponse(FRONTEND_DIST / "favicon.svg", media_type="image/svg+xml")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str):
            return FileResponse(FRONTEND_DIST / "index.html")

    return app
