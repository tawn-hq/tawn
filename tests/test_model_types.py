import pytest
from pydantic import ValidationError

from tawn.model.types import ErrorKind, Message, ModelError, ModelResponse


def test_error_kinds_cover_spec_table():
    kinds = {k.name for k in ErrorKind}
    assert {
        "RATE_LIMIT",
        "QUOTA_EXHAUSTED",
        "CONTEXT_OVERFLOW",
        "SERVER_ERROR",
        "TIMEOUT",
        "AUTH",
        "UNKNOWN",
    } <= kinds


def test_model_error_carries_kind_and_provider():
    err = ModelError("boom", kind=ErrorKind.RATE_LIMIT, provider="gemini")
    assert err.kind is ErrorKind.RATE_LIMIT
    assert err.provider == "gemini"
    assert "boom" in str(err)


def test_message_validates_role():
    Message(role="user", content="hi")
    with pytest.raises(ValidationError):
        Message(role="robot", content="hi")


def test_response_shape():
    r = ModelResponse(text="hey", model="m", provider="p", tokens_in=3, tokens_out=5)
    assert r.tokens_out == 5
