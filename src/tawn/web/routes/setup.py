"""Setup routes — web equivalent of `tawn setup`'s steps."""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from tawn.config import settings
from tawn.dbsetup import ensure_database
from tawn.home import init_home, tawn_home
from tawn.model.catalog import explore
from tawn.model.keys import KeyStorageError, key_status, set_key
from tawn.model.providers.ollama import OllamaProvider, total_ram_bytes

router = APIRouter()


@router.post("/init")
def setup_init():
    home = tawn_home()
    created = init_home(home)
    return {"created": [str(p) for p in created]}


@router.post("/db")
def setup_db():
    st = ensure_database(settings().db_url)
    return {"server_up": st.server_up, "can_connect": st.can_connect, "detail": st.detail}


@router.get("/models")
def setup_models():
    ram = total_ram_bytes()
    installed = {m["name"] for m in OllamaProvider().installed_models()}
    return explore(ram, installed)


@router.post("/model/pull")
def setup_model_pull(model: str):
    provider = OllamaProvider()

    def events():
        try:
            collected: list[dict] = []
            provider.pull(model, on_progress=collected.append)
            for ev in collected:
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/keys/{provider}")
def keys_get(provider: str):
    return {"status": key_status(provider)}


class KeyBody(BaseModel):
    key: str


@router.post("/keys/{provider}")
def keys_post(provider: str, body: KeyBody):
    try:
        set_key(provider, body.key)
    except KeyStorageError as e:
        return {"ok": False, "detail": str(e)}
    return {"ok": True}
