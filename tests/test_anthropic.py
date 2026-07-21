from types import SimpleNamespace

import anthropic as anthropic_sdk
import httpx
import pytest

from tawn.model.providers.anthropic import AnthropicProvider
from tawn.model.types import ErrorKind, Message, ModelError

MSGS = [
    Message(role="system", content="be brief"),
    Message(role="user", content="hello"),
]


def ok_response(text="hi there", tin=9, tout=4):
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        usage=SimpleNamespace(input_tokens=tin, output_tokens=tout),
        stop_reason="end_turn",
    )


class FakeMessages:
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
    return SimpleNamespace(messages=FakeMessages(result=result, exc=exc))


def sdk_error(cls, code):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(code, request=req, text="{}")
    return cls(message=str(code), response=resp, body=None)


def test_complete_maps_response_and_tokens():
    client = fake_client(result=ok_response())
    r = AnthropicProvider(api_key="sk-test", client=client).complete(MSGS)
    assert r.text == "hi there"  # thinking blocks excluded
    assert r.provider == "anthropic" and r.tokens_in == 9 and r.tokens_out == 4
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-4-8"
    assert call["system"] == "be brief"  # system goes to the system param
    assert all(m["role"] in ("user", "assistant") for m in call["messages"])


def test_classify_errors():
    p = AnthropicProvider(api_key="sk-test", client=fake_client())
    assert p.classify_error(sdk_error(anthropic_sdk.RateLimitError, 429)) is ErrorKind.RATE_LIMIT
    assert p.classify_error(sdk_error(anthropic_sdk.AuthenticationError, 401)) is ErrorKind.AUTH
    assert p.classify_error(sdk_error(anthropic_sdk.PermissionDeniedError, 403)) is ErrorKind.AUTH
    assert p.classify_error(sdk_error(anthropic_sdk.InternalServerError, 500)) is ErrorKind.SERVER_ERROR
    assert p.classify_error(anthropic_sdk.APITimeoutError(request=httpx.Request("POST", "https://x"))) is ErrorKind.TIMEOUT
    assert p.classify_error(anthropic_sdk.APIConnectionError(request=httpx.Request("POST", "https://x"))) is ErrorKind.SERVER_ERROR


def test_credit_exhausted_maps_to_quota():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(400, request=req, text="{}")
    exc = anthropic_sdk.BadRequestError(
        message="Your credit balance is too low", response=resp, body=None
    )
    p = AnthropicProvider(api_key="sk-test", client=fake_client())
    assert p.classify_error(exc) is ErrorKind.QUOTA_EXHAUSTED


def test_context_overflow_maps():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(400, request=req, text="{}")
    exc = anthropic_sdk.BadRequestError(
        message="prompt is too long: 250000 tokens", response=resp, body=None
    )
    p = AnthropicProvider(api_key="sk-test", client=fake_client())
    assert p.classify_error(exc) is ErrorKind.CONTEXT_OVERFLOW


def test_error_never_leaks_api_key():
    exc = sdk_error(anthropic_sdk.InternalServerError, 500)
    exc.message = "boom key=sk-SECRET123"
    p = AnthropicProvider(api_key="sk-SECRET123", client=fake_client(exc=exc))
    with pytest.raises(ModelError) as ei:
        p.complete(MSGS)
    assert "sk-SECRET123" not in str(ei.value)
    assert ei.value.kind is ErrorKind.SERVER_ERROR


def test_stream_complete_yields_chunks_then_done():
    class FakeStream:
        def __init__(self):
            self.text_stream = iter(["hi ", "there"])

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return ok_response(text="hi there", tin=9, tout=4)

    class FakeMessagesStreaming(FakeMessages):
        def stream(self, **kwargs):
            self.calls.append(kwargs)
            return FakeStream()

    client = SimpleNamespace(messages=FakeMessagesStreaming())
    p = AnthropicProvider(api_key="sk-test", client=client)
    chunks = list(p.stream_complete(MSGS))
    text_chunks = [c for c in chunks if not c.done]
    assert "".join(c.text for c in text_chunks) == "hi there"
    final = chunks[-1]
    assert final.done and final.tokens_in == 9 and final.tokens_out == 4
