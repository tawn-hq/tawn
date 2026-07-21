"""Chat routes — SSE streaming through Router.stream(), same as CLI."""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from tawn.home import tawn_home
from tawn.model.identity import with_baseline
from tawn.model.router import default_router, usable_models
from tawn.model.types import Message

router = APIRouter()


@router.get("/models")
def chat_models():
    return usable_models(tawn_home())


class ChatBody(BaseModel):
    history: list[dict]
    sensitive: bool = False


@router.post("/stream")
def chat_stream(body: ChatBody):
    home = tawn_home()
    msgs = with_baseline(
        [Message(role=m["role"], content=m["content"]) for m in body.history], home
    )
    r = default_router(home)

    def events():
        for chunk in r.stream(msgs, sensitive=body.sensitive):
            if chunk.error:
                yield f"data: {json.dumps({'type': 'error', 'message': chunk.error})}\n\n"
                return
            if chunk.done:
                yield f"data: {json.dumps({'type': 'done', 'tokens_in': chunk.tokens_in, 'tokens_out': chunk.tokens_out})}\n\n"
                return
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk.text})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
