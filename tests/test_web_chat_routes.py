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


# ── tool calling in chat (Stage 10) ──────────────────────────────────────────

def _client(tawn_home, monkeypatch):
    import tawn.web.routes.chat as chat_mod

    monkeypatch.setattr(
        chat_mod, "default_router",
        lambda home, target=None: Router([EchoProvider()], Ledger(home / "ledger.jsonl")),
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/chat")
    return TestClient(app)


def _sse_types(text: str) -> list[str]:
    import json as _json

    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                out.append(_json.loads(line[6:]).get("type"))
            except Exception:
                pass
    return out


def test_tools_are_off_by_default(tawn_home, monkeypatch):
    """An existing client must see exactly its previous behaviour."""
    built = []
    import tawn.model.tools as tools_mod

    monkeypatch.setattr(
        tools_mod.ToolRegistry, "build",
        classmethod(lambda cls, home, grants=None: built.append(home) or cls(home)),
    )
    client = _client(tawn_home, monkeypatch)
    r = client.post("/api/chat/stream", json={"history": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert built == []  # the registry was never even constructed


def test_a_tool_call_is_reported_before_the_answer_streams(tawn_home, monkeypatch):
    import tawn.model.agent as agent_mod
    import tawn.model.tools as tools_mod
    from tawn.model.tools import ToolRegistry
    from tawn.model.types import ToolSpec

    def _build(cls, home, grants=None):
        reg = ToolRegistry(home)
        reg.register(
            ToolSpec(name="recall", description="d", parameters={"type": "object"}),
            lambda **kw: "you chose pgvector",
        )
        return reg

    monkeypatch.setattr(tools_mod.ToolRegistry, "build", classmethod(_build))

    class Result:
        tool_calls = [object()]
        truncated = False

        def trace(self):
            return [{"name": "recall", "arguments": {"query": "x"},
                     "ok": True, "result": "you chose pgvector"}]

    monkeypatch.setattr(agent_mod, "run", lambda *a, **k: Result())

    client = _client(tawn_home, monkeypatch)
    r = client.post("/api/chat/stream", json={
        "history": [{"role": "user", "content": "what did I choose"}],
        "tools": True,
    })
    types_seen = _sse_types(r.text)
    assert "tool" in types_seen
    assert types_seen.index("tool") < types_seen.index("done")
    assert "you chose pgvector" in r.text


def test_a_tool_failure_does_not_cost_the_user_their_answer(tawn_home, monkeypatch):
    import tawn.model.tools as tools_mod

    def _boom(cls, home, grants=None):
        raise RuntimeError("registry exploded")

    monkeypatch.setattr(tools_mod.ToolRegistry, "build", classmethod(_boom))

    client = _client(tawn_home, monkeypatch)
    r = client.post("/api/chat/stream", json={
        "history": [{"role": "user", "content": "hi"}], "tools": True,
    })
    types_seen = _sse_types(r.text)
    assert "notice" in types_seen
    assert "done" in types_seen  # the turn still completed


# ── attachments (parsed on attach, referenced by id) ─────────────────────────

def test_attach_parses_immediately_and_returns_metadata(tawn_home, monkeypatch):
    client = _client(tawn_home, monkeypatch)
    r = client.post("/api/chat/attach", files={"file": ("notes.txt", b"hello world", "text/plain")})
    body = r.json()
    assert body["ok"] is True
    assert body["format"] == "text"
    assert body["chars"] == 11
    assert body["id"]
    # The payload never rides back to the browser — only what the UI shows.
    assert "text" not in body


def test_attach_reports_a_bad_file_without_raising(tawn_home, monkeypatch):
    client = _client(tawn_home, monkeypatch)
    body = client.post("/api/chat/attach", files={"file": ("empty.txt", b"", "text/plain")}).json()
    assert body["ok"] is False
    assert "empty" in body["error"]


def test_attached_text_reaches_the_model_for_that_turn(tawn_home, monkeypatch):
    client = _client(tawn_home, monkeypatch)
    attach_id = client.post(
        "/api/chat/attach",
        files={"file": ("brief.txt", b"PROJECT CODENAME ORCHID", "text/plain")},
    ).json()["id"]

    r = client.post("/api/chat/stream", json={
        "history": [{"role": "user", "content": "summarise it"}],
        "attachments": [attach_id],
    })
    # EchoProvider echoes the last message, so the injected text is visible.
    assert "ORCHID" in r.text
    assert "ATTACHED DOCUMENTS" in r.text


def test_an_unknown_attachment_id_does_not_break_the_turn(tawn_home, monkeypatch):
    client = _client(tawn_home, monkeypatch)
    r = client.post("/api/chat/stream", json={
        "history": [{"role": "user", "content": "hi"}],
        "attachments": ["deadbeef"],
    })
    assert r.status_code == 200
    assert "done" in _sse_types(r.text)


def test_a_turn_with_no_attachments_is_unchanged(tawn_home, monkeypatch):
    client = _client(tawn_home, monkeypatch)
    r = client.post("/api/chat/stream", json={"history": [{"role": "user", "content": "plain"}]})
    assert "ATTACHED DOCUMENTS" not in r.text


def test_detaching_removes_it(tawn_home, monkeypatch):
    client = _client(tawn_home, monkeypatch)
    attach_id = client.post(
        "/api/chat/attach", files={"file": ("a.txt", b"x", "text/plain")}
    ).json()["id"]
    assert client.delete(f"/api/chat/attach/{attach_id}").json()["ok"] is True
    assert client.delete(f"/api/chat/attach/{attach_id}").json()["ok"] is False
