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
    def __init__(self, chat_result=None, chat_exc=None):
        self.chat_result = chat_result
        self.chat_exc = chat_exc
        self.calls: list[dict] = []

    def chat(self, *, model, messages):
        self.calls.append({"model": model, "messages": messages})
        if self.chat_exc:
            raise self.chat_exc
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
