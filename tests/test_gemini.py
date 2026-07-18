from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors

from tawn.model.providers.gemini import GeminiProvider
from tawn.model.types import ErrorKind, Message, ModelError

MSGS = [
    Message(role="system", content="be brief"),
    Message(role="user", content="hello"),
]


class FakeModels:
    def __init__(self, result=None, exc=None, listing=None):
        self.result = result
        self.exc = exc
        self.listing = listing or []
        self.calls: list[dict] = []

    def generate_content(self, *, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.exc:
            raise self.exc
        return self.result

    def list(self):
        if self.exc:
            raise self.exc
        return iter(self.listing)


def fake_client(result=None, exc=None):
    return SimpleNamespace(models=FakeModels(result=result, exc=exc))


def ok_response(text="hi there", tin=9, tout=4):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(prompt_token_count=tin, candidates_token_count=tout),
    )


def api_error(code, status="", message=""):
    return genai_errors.APIError(
        code, {"error": {"status": status, "message": message}}
    )


def test_complete_maps_response_and_tokens():
    client = fake_client(result=ok_response())
    r = GeminiProvider(api_key="sk-test", client=client).complete(MSGS)
    assert r.text == "hi there"
    assert r.provider == "gemini" and r.tokens_in == 9 and r.tokens_out == 4
    call = client.models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    # system message becomes system_instruction, not a content turn
    assert call["config"].system_instruction == "be brief"
    assert all(c["role"] in ("user", "model") for c in call["contents"])


def test_429_quota_vs_rate_limit():
    p = GeminiProvider(api_key="sk-test", client=fake_client())
    assert p.classify_error(api_error(429, status="RESOURCE_EXHAUSTED")) is ErrorKind.QUOTA_EXHAUSTED
    assert p.classify_error(api_error(429, message="slow down")) is ErrorKind.RATE_LIMIT


def test_400_token_overflow_and_auth_and_5xx():
    p = GeminiProvider(api_key="sk-test", client=fake_client())
    assert p.classify_error(api_error(400, message="input token count exceeds")) is ErrorKind.CONTEXT_OVERFLOW
    assert p.classify_error(api_error(403, status="PERMISSION_DENIED")) is ErrorKind.AUTH
    assert p.classify_error(api_error(500, status="INTERNAL")) is ErrorKind.SERVER_ERROR
    assert p.classify_error(httpx.ReadTimeout("t")) is ErrorKind.TIMEOUT


def sdk_model(name, actions, in_limit=1_000_000, out_limit=8192, desc="d"):
    return SimpleNamespace(
        name=name,
        display_name=name.split("/")[-1],
        description=desc,
        supported_actions=actions,
        input_token_limit=in_limit,
        output_token_limit=out_limit,
    )


def test_available_models_filters_to_generate_content():
    listing = [
        sdk_model("models/gemini-2.5-flash", ["generateContent", "countTokens"]),
        sdk_model("models/embedding-001", ["embedContent"]),
        sdk_model("models/gemini-2.5-pro", ["generateContent"]),
    ]
    client = SimpleNamespace(models=FakeModels(listing=listing))
    rows = GeminiProvider(api_key="sk-test", client=client).available_models()
    names = [r["name"] for r in rows]
    assert names == ["gemini-2.5-flash", "gemini-2.5-pro"]  # models/ prefix stripped
    assert rows[0]["context_tokens"] == 1_000_000
    assert rows[0]["provider"] == "gemini"


def test_available_models_empty_on_error():
    client = SimpleNamespace(models=FakeModels(exc=api_error(500, status="INTERNAL")))
    assert GeminiProvider(api_key="sk-test", client=client).available_models() == []


def test_error_never_leaks_api_key():
    exc = api_error(500, status="INTERNAL", message="boom key=sk-SECRET123")
    p = GeminiProvider(api_key="sk-SECRET123", client=fake_client(exc=exc))
    with pytest.raises(ModelError) as ei:
        p.complete(MSGS)
    assert "sk-SECRET123" not in str(ei.value)
    assert ei.value.kind is ErrorKind.SERVER_ERROR
