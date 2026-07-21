"""Tawn web viewer — JSON API only (design spec: web-viewer-v2).

React SPA in frontend/dist is served as static files with SPA fallback;
every domain's api_router (if any) mounts at /api/<name>.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

from tawn.domains.registry import enabled_domains
from tawn.home import tawn_home

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="tawn", docs_url=None, redoc_url=None)

    @app.get("/api/status")
    def status():
        home = tawn_home()
        return {"initialized": (home / "raw").is_dir()}

    @app.get("/api/domains")
    def domains():
        return [
            {"name": d.name, "label": d.label, "nav": d.nav}
            for d in enabled_domains(home=tawn_home())
        ]

    from tawn.web.routes.setup import router as setup_router
    from tawn.web.routes.chat import router as chat_router
    from tawn.web.routes.grants import router as grants_router
    from tawn.web.routes.domains import router as domain_create_router
    from tawn.web.routes.profile import router as profile_router
    from tawn.web.routes.history import router as history_router
    from tawn.web.routes.memory import router as memory_router

    app.include_router(setup_router, prefix="/api/setup")
    app.include_router(chat_router, prefix="/api/chat")
    app.include_router(grants_router, prefix="/api")
    app.include_router(domain_create_router, prefix="/api/domains")
    app.include_router(profile_router, prefix="/api")
    app.include_router(history_router, prefix="/api")
    app.include_router(memory_router, prefix="/api")

    @app.get("/api/models")
    def all_models():
        from tawn.model.router import usable_models
        return usable_models(tawn_home())

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
