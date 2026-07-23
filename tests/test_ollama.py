from types import SimpleNamespace

import httpx
from ollama import ResponseError

from tawn.model.providers.ollama import OllamaProvider
from tawn.model.types import ErrorKind, Message

MSGS = [Message(role="user", content="hello")]


def chat_response(text="hi there", tin=12, tout=7):
    return SimpleNamespace(
        message=SimpleNamespace(content=text),
        prompt_eval_count=tin,
        eval_count=tout,
    )


class FakeClient:
    def __init__(self, chat_result=None, chat_exc=None, chat_stream=None):
        self.chat_result = chat_result
        self.chat_exc = chat_exc
        self.chat_stream = chat_stream or []
        self.calls: list[dict] = []

    def chat(self, *, model, messages, stream=False):
        self.calls.append({"model": model, "messages": messages, "stream": stream})
        if self.chat_exc:
            raise self.chat_exc
        if stream:
            return iter(self.chat_stream)
        return self.chat_result


def test_complete_maps_response_and_tokens():
    client = FakeClient(chat_result=chat_response())
    r = OllamaProvider(client=client).complete(MSGS)
    assert r.text == "hi there"
    assert r.provider == "ollama" and r.tokens_in == 12 and r.tokens_out == 7
    assert client.calls[0]["model"] == "qwen2.5:7b"
    assert client.calls[0]["messages"] == [{"role": "user", "content": "hello"}]


def test_classify_connect_error_is_server_error():
    p = OllamaProvider(client=FakeClient())
    assert p.classify_error(httpx.ConnectError("refused")) is ErrorKind.SERVER_ERROR
    assert p.classify_error(httpx.ReadTimeout("slow")) is ErrorKind.TIMEOUT
    assert p.classify_error(ResponseError("boom", 500)) is ErrorKind.SERVER_ERROR


def test_count_tokens_estimates():
    assert OllamaProvider(client=FakeClient()).count_tokens(MSGS) >= 1


def test_stream_complete_yields_chunks_then_done():
    def make_chunk(content=None, done=False, prompt_eval_count=None, eval_count=None):
        return SimpleNamespace(
            message=SimpleNamespace(content=content) if content is not None else None,
            done=done,
            prompt_eval_count=prompt_eval_count,
            eval_count=eval_count,
        )

    client = FakeClient(chat_stream=[
        make_chunk(content="hi "),
        make_chunk(content="there", done=True, prompt_eval_count=12, eval_count=7),
    ])
    p = OllamaProvider(client=client)
    chunks = list(p.stream_complete(MSGS))
    text_chunks = [c for c in chunks if not c.done]
    assert "".join(c.text for c in text_chunks) == "hi there"
    final = chunks[-1]
    assert final.done and final.tokens_in == 12 and final.tokens_out == 7
    assert client.calls[0]["stream"] is True
