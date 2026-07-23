from fastapi import FastAPI
from fastapi.testclient import TestClient

from tawn.model.ledger import Ledger
from tawn.model.router import Router
from tawn.model.types import StreamChunk
from tawn.web.routes.chat import router


class EchoProvider:
    name = "ollama"
    locality = "local"
    model = "ollama-model"

    def stream_complete(self, msgs, model=None):
        yield StreamChunk(text=f"echo: {msgs[-1].content}")
        yield StreamChunk(text="", done=True, tokens_in=1, tokens_out=1)

    def complete(self, msgs, model=None):
        raise NotImplementedError

    def count_tokens(self, msgs):
        return 1

    def classify_error(self, exc):
        from tawn.model.types import ErrorKind

        return ErrorKind.UNKNOWN


def test_chat_stream_returns_sse_events(tawn_home, monkeypatch):
    import tawn.web.routes.chat as chat_mod

    monkeypatch.setattr(
        chat_mod,
        "default_router",
        lambda home, target=None: Router([EchoProvider()], Ledger(home / "ledger.jsonl")),
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/chat")
    client = TestClient(app)
    resp = client.post(
        "/api/chat/stream", json={"history": [{"role": "user", "content": "hi"}]}
    )
    assert resp.status_code == 200
    assert "echo: hi" in resp.text
    assert "data:" in resp.text
