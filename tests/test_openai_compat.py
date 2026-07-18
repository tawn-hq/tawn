from types import SimpleNamespace

import httpx
import openai as openai_sdk
import pytest

from tawn.model.providers.openai_compat import (
    DEEPSEEK_BASE,
    OpenAICompatProvider,
    deepseek_provider,
    openai_provider,
)
from tawn.model.types import ErrorKind, Message, ModelError

MSGS = [
    Message(role="system", content="be brief"),
    Message(role="user", content="hello"),
]


def ok_response(text="hi there", tin=9, tout=4):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=tin, completion_tokens=tout),
    )


class FakeCompletions:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.result


def fake_client(result=None, exc=None):
    return SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions(result=result, exc=exc))
    )


def sdk_error(cls, code, message="err"):
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp = httpx.Response(code, request=req, text="{}")
    return cls(message, response=resp, body=None)


def test_complete_maps_response_and_tokens():
    client = fake_client(result=ok_response())
    p = OpenAICompatProvider(name="openai", api_key="sk-test", model="gpt-5.1", client=client)
    r = p.complete(MSGS)
    assert r.text == "hi there"
    assert r.provider == "openai" and r.tokens_in == 9 and r.tokens_out == 4
    call = client.chat.completions.calls[0]
    assert call["model"] == "gpt-5.1"
    # system message passes straight through in openai format
    assert call["messages"][0] == {"role": "system", "content": "be brief"}


def test_factories_set_name_and_base():
    o = openai_provider("sk-test")
    d = deepseek_provider("sk-test")
    assert o.name == "openai" and o.locality == "cloud"
    assert d.name == "deepseek" and d.locality == "cloud"
    assert DEEPSEEK_BASE == "https://api.deepseek.com"


def test_classify_errors():
    p = OpenAICompatProvider(name="openai", api_key="sk-test", model="m", client=fake_client())
    assert p.classify_error(sdk_error(openai_sdk.RateLimitError, 429)) is ErrorKind.RATE_LIMIT
    quota = sdk_error(openai_sdk.RateLimitError, 429, message="insufficient_quota: billing")
    assert p.classify_error(quota) is ErrorKind.QUOTA_EXHAUSTED
    assert p.classify_error(sdk_error(openai_sdk.AuthenticationError, 401)) is ErrorKind.AUTH
    assert p.classify_error(sdk_error(openai_sdk.PermissionDeniedError, 403)) is ErrorKind.AUTH
    assert p.classify_error(sdk_error(openai_sdk.InternalServerError, 500)) is ErrorKind.SERVER_ERROR
    overflow = sdk_error(openai_sdk.BadRequestError, 400, message="context_length_exceeded")
    assert p.classify_error(overflow) is ErrorKind.CONTEXT_OVERFLOW
    assert p.classify_error(
        openai_sdk.APITimeoutError(request=httpx.Request("POST", "https://x"))
    ) is ErrorKind.TIMEOUT
    assert p.classify_error(
        openai_sdk.APIConnectionError(request=httpx.Request("POST", "https://x"))
    ) is ErrorKind.SERVER_ERROR


def test_error_never_leaks_api_key():
    exc = sdk_error(openai_sdk.InternalServerError, 500, message="boom key=sk-SECRET123")
    p = OpenAICompatProvider(
        name="openai", api_key="sk-SECRET123", model="m", client=fake_client(exc=exc)
    )
    with pytest.raises(ModelError) as ei:
        p.complete(MSGS)
    assert "sk-SECRET123" not in str(ei.value)
    assert ei.value.kind is ErrorKind.SERVER_ERROR
