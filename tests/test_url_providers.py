from unittest.mock import MagicMock
import pytest
from tawn.model.providers.openai_compat import openrouter_provider, kimi_provider, qwen_provider
from tawn.model.types import Message


def _fake_client(text="ok"):
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = text
    client.chat.completions.create.return_value = MagicMock(
        choices=[choice],
        usage=MagicMock(prompt_tokens=5, completion_tokens=3),
    )
    return client


def test_openrouter_provider_name():
    p = openrouter_provider("key")
    assert p.name == "openrouter"


def test_kimi_provider_name():
    p = kimi_provider("key")
    assert p.name == "kimi"


def test_qwen_provider_name():
    p = qwen_provider("key")
    assert p.name == "qwen"


def test_openrouter_complete():
    p = openrouter_provider("key")
    p._client = _fake_client("hello from openrouter")
    resp = p.complete([Message(role="user", content="hi")])
    assert resp.text == "hello from openrouter"
    assert resp.provider == "openrouter"


def test_kimi_complete():
    p = kimi_provider("key")
    p._client = _fake_client("hello from kimi")
    resp = p.complete([Message(role="user", content="hi")])
    assert resp.text == "hello from kimi"
    assert resp.provider == "kimi"


def test_qwen_complete():
    p = qwen_provider("key")
    p._client = _fake_client("hello from qwen")
    resp = p.complete([Message(role="user", content="hi")])
    assert resp.text == "hello from qwen"
    assert resp.provider == "qwen"
