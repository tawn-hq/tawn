"""Tool encoding/decoding per vendor, and the refuse-don't-drop rule."""

import json
import types

import pytest

from tawn.model.toolwire import (
    anthropic_calls, anthropic_messages, anthropic_tools, gemini_calls,
    gemini_parts, gemini_tools, openai_calls, openai_messages, openai_tools,
)
from tawn.model.types import Message, ToolCall, ToolSpec, ToolsUnsupported

SPEC = ToolSpec(
    name="recall",
    description="search memory",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "q"}},
        "required": ["query"],
        "additionalProperties": False,   # vendor-unsupported key, must be pruned
    },
)

CONVO = [
    Message(role="user", content="what did I decide"),
    Message(role="assistant", content="",
            tool_calls=[ToolCall(id="c1", name="recall", arguments={"query": "x"})]),
    Message(role="tool", content="you chose pgvector", tool_call_id="c1"),
]


def _obj(**kw):
    return types.SimpleNamespace(**kw)


# ── schema pruning ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("encoder,path", [
    (anthropic_tools, lambda t: t[0]["input_schema"]),
    (openai_tools, lambda t: t[0]["function"]["parameters"]),
    (gemini_tools, lambda t: t[0]["function_declarations"][0]["parameters"]),
])
def test_unsupported_schema_keys_are_pruned(encoder, path):
    schema = path(encoder([SPEC]))
    assert "additionalProperties" not in schema
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["required"] == ["query"]


# ── Anthropic ────────────────────────────────────────────────────────────────

def test_anthropic_encodes_tool_use_and_result_blocks():
    msgs = anthropic_messages(CONVO)
    assistant = msgs[1]
    assert assistant["role"] == "assistant"
    assert assistant["content"][0]["type"] == "tool_use"
    assert assistant["content"][0]["id"] == "c1"
    result = msgs[2]
    assert result["content"][0]["type"] == "tool_result"
    assert result["content"][0]["tool_use_id"] == "c1"


def test_anthropic_decodes_a_tool_use_block():
    resp = _obj(content=[
        _obj(type="text", text="thinking"),
        _obj(type="tool_use", id="abc", name="recall", input={"query": "x"}),
    ])
    calls = anthropic_calls(resp)
    assert [(c.id, c.name, c.arguments) for c in calls] == [("abc", "recall", {"query": "x"})]


def test_anthropic_decodes_nothing_from_a_plain_answer():
    assert anthropic_calls(_obj(content=[_obj(type="text", text="hi")])) == []


# ── OpenAI ───────────────────────────────────────────────────────────────────

def test_openai_encodes_tool_calls_and_tool_role():
    msgs = openai_messages(CONVO)
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "recall"
    assert json.loads(msgs[1]["tool_calls"][0]["function"]["arguments"]) == {"query": "x"}
    assert msgs[2] == {"role": "tool", "tool_call_id": "c1", "content": "you chose pgvector"}


def test_openai_decodes_a_tool_call():
    resp = _obj(choices=[_obj(message=_obj(tool_calls=[
        _obj(id="t1", function=_obj(name="recall", arguments='{"query": "x"}'))
    ]))])
    calls = openai_calls(resp)
    assert (calls[0].id, calls[0].name, calls[0].arguments) == ("t1", "recall", {"query": "x"})


def test_openai_malformed_arguments_do_not_kill_the_turn():
    """A model can emit invalid JSON; the tool should report a clear argument
    error rather than the decode raising."""
    resp = _obj(choices=[_obj(message=_obj(tool_calls=[
        _obj(id="t1", function=_obj(name="recall", arguments="{not json"))
    ]))])
    assert openai_calls(resp)[0].arguments == {}


def test_openai_decodes_nothing_from_a_plain_answer():
    assert openai_calls(_obj(choices=[_obj(message=_obj(tool_calls=None))])) == []


# ── Gemini ───────────────────────────────────────────────────────────────────

def test_gemini_encodes_model_role_and_function_response():
    parts = gemini_parts(CONVO)
    assert parts[0]["role"] == "user"
    assert parts[1]["role"] == "model"
    assert parts[1]["parts"][0]["function_call"]["name"] == "recall"
    assert parts[2]["parts"][0]["function_response"]["response"]["result"] == (
        "you chose pgvector"
    )


def test_gemini_decodes_a_function_call_and_synthesises_an_id():
    resp = _obj(candidates=[_obj(content=_obj(parts=[
        _obj(function_call=_obj(name="recall", args={"query": "x"}))
    ]))])
    calls = gemini_calls(resp)
    assert calls[0].name == "recall"
    assert calls[0].arguments == {"query": "x"}
    # Gemini issues no call ids, but the loop needs one to pair results.
    assert calls[0].id


def test_gemini_decodes_nothing_from_a_plain_answer():
    resp = _obj(candidates=[_obj(content=_obj(parts=[_obj(function_call=None)]))])
    assert gemini_calls(resp) == []


# ── refuse, don't drop ───────────────────────────────────────────────────────

def _resp(content="", tool_calls=None):
    return _obj(
        message=_obj(content=content, tool_calls=tool_calls),
        prompt_eval_count=1,
        eval_count=2,
    )


def _ollama(model="qwen2.5:7b", client=None):
    from tawn.model.providers.ollama import OllamaProvider

    p = OllamaProvider.__new__(OllamaProvider)
    p.model = model
    p._client = client
    # Class-level cache: reset so one test cannot pin another into prompted mode.
    OllamaProvider._NO_NATIVE_TOOLS = set()
    return p


def test_ollama_uses_native_tools_when_the_model_supports_them():
    seen = {}

    class Client:
        def chat(self, model, messages, tools=None):
            seen["tools"] = tools
            return _resp(tool_calls=[
                _obj(function=_obj(name="recall", arguments={"query": "x"}))
            ])

    resp = _ollama(client=Client()).complete(
        [Message(role="user", content="hi")], tools=[SPEC]
    )
    assert seen["tools"][0]["function"]["name"] == "recall"
    assert resp.tool_calls[0].name == "recall"
    assert resp.tool_calls[0].arguments == {"query": "x"}
    assert resp.tool_calls[0].id  # synthesised, since Ollama issues none


def test_ollama_falls_back_to_prompted_mode_when_native_is_unsupported():
    """A model without a tools API still gets to use tools."""
    calls = []

    class Client:
        def chat(self, model, messages, tools=None):
            calls.append(bool(tools))
            if tools:
                raise RuntimeError("registry.ollama.ai: model does not support tools")
            return _resp(
                content='<tool_call>{"name": "recall", "arguments": {"query": "x"}}</tool_call>'
            )

    p = _ollama(client=Client())
    resp = p.complete([Message(role="user", content="hi")], tools=[SPEC])
    assert calls == [True, False]  # tried native, then prompted
    assert resp.tool_calls[0].name == "recall"
    assert resp.tool_calls[0].arguments == {"query": "x"}
    assert resp.text == ""  # the block is stripped from the prose


def test_the_unsupported_result_is_cached_so_native_is_not_retried():
    calls = []

    class Client:
        def chat(self, model, messages, tools=None):
            calls.append(bool(tools))
            if tools:
                raise RuntimeError("model does not support tools")
            return _resp(content="plain answer")

    p = _ollama(client=Client())
    p.complete([Message(role="user", content="a")], tools=[SPEC])
    p.complete([Message(role="user", content="b")], tools=[SPEC])
    # Native attempted once, not once per call.
    assert calls.count(True) == 1


def test_a_real_ollama_error_is_not_mistaken_for_missing_tool_support():
    from tawn.model.types import ModelError

    class Client:
        def chat(self, model, messages, tools=None):
            raise RuntimeError("connection refused")

    with pytest.raises(ModelError):
        _ollama(client=Client()).complete(
            [Message(role="user", content="hi")], tools=[SPEC]
        )


def test_ollama_without_tools_is_unaffected():
    """The no-tools path must stay exactly as it was."""
    seen = {}

    class Client:
        def chat(self, model, messages):
            seen["messages"] = messages
            return _resp(content="hi")

    resp = _ollama(client=Client()).complete([Message(role="user", content="hello")])
    assert resp.text == "hi"
    assert seen["messages"] == [{"role": "user", "content": "hello"}]
    assert resp.tool_calls == []


# ── the ladder on OpenAI-compatible endpoints ────────────────────────────────

def _compat(model="gpt-4o", create=None):
    from tawn.model.providers.openai_compat import OpenAICompatProvider

    p = OpenAICompatProvider.__new__(OpenAICompatProvider)
    p.model = model
    p.name = "openai"
    p._api_key = "sk-test"  # `_redact` reads it on the error path
    p._client = _obj(chat=_obj(completions=_obj(create=create)))
    OpenAICompatProvider._NO_NATIVE_TOOLS = set()
    return p


def _choice(content="", tool_calls=None):
    return _obj(
        choices=[_obj(message=_obj(content=content, tool_calls=tool_calls))],
        usage=_obj(prompt_tokens=1, completion_tokens=2),
    )


def test_openrouter_gets_native_tools_through_the_compat_adapter():
    """OpenRouter is OpenAI-compatible, so it needs no special casing."""
    seen = {}

    def create(**kw):
        seen.update(kw)
        return _choice(tool_calls=[
            _obj(id="t1", function=_obj(name="recall", arguments='{"query":"x"}'))
        ])

    p = _compat(model="anthropic/claude-opus-4", create=create)
    p.name = "openrouter"
    resp = p.complete([Message(role="user", content="hi")], tools=[SPEC])
    assert seen["tools"][0]["function"]["name"] == "recall"
    assert resp.tool_calls[0].name == "recall"


def test_a_compat_endpoint_without_tools_falls_back_to_prompted():
    attempts = []

    def create(**kw):
        attempts.append("tools" in kw)
        if "tools" in kw:
            raise RuntimeError("400: unknown parameter 'tools'")
        return _choice(
            content='<tool_call>{"name": "recall", "arguments": {"query": "x"}}</tool_call>'
        )

    resp = _compat(create=create).complete(
        [Message(role="user", content="hi")], tools=[SPEC]
    )
    assert attempts == [True, False]
    assert resp.tool_calls[0].name == "recall"
    assert resp.text == ""


def test_the_compat_fallback_is_remembered_per_model():
    attempts = []

    def create(**kw):
        attempts.append("tools" in kw)
        if "tools" in kw:
            raise RuntimeError("tools not supported")
        return _choice(content="plain")

    p = _compat(create=create)
    p.complete([Message(role="user", content="a")], tools=[SPEC])
    p.complete([Message(role="user", content="b")], tools=[SPEC])
    assert attempts.count(True) == 1


def test_a_genuine_compat_error_still_raises():
    from tawn.model.types import ModelError

    def create(**kw):
        raise RuntimeError("401 unauthorized")

    with pytest.raises(ModelError):
        _compat(create=create).complete(
            [Message(role="user", content="hi")], tools=[SPEC]
        )


def test_the_compat_no_tools_path_is_unchanged():
    seen = {}

    def create(**kw):
        seen.update(kw)
        return _choice(content="hi")

    resp = _compat(create=create).complete([Message(role="user", content="hello")])
    assert "tools" not in seen
    assert seen["messages"] == [{"role": "user", "content": "hello"}]
    assert resp.text == "hi"
    assert resp.tool_calls == []


# ── the ladder is universal ──────────────────────────────────────────────────

def test_every_adapter_declares_a_prompted_fallback():
    """No provider may be a dead end for tool calling.

    A model that cannot call tools makes Tawn's whole tool surface work only on
    the expensive providers, which is backwards for a local-first system.
    """
    from tawn.model.providers.anthropic import AnthropicProvider
    from tawn.model.providers.gemini import GeminiProvider
    from tawn.model.providers.ollama import OllamaProvider
    from tawn.model.providers.openai_compat import OpenAICompatProvider

    for cls in (AnthropicProvider, GeminiProvider, OllamaProvider, OpenAICompatProvider):
        assert hasattr(cls, "_complete_prompted"), cls.__name__
        assert hasattr(cls, "_NO_NATIVE_TOOLS"), cls.__name__


def test_gemini_falls_back_to_prompted_mode():
    from tawn.model.providers.gemini import GeminiProvider

    attempts = []

    class Models:
        def generate_content(self, model, contents, config):
            has_tools = getattr(config, "tools", None) is not None
            attempts.append(has_tools)
            if has_tools:
                raise RuntimeError("400 tools is not supported for this model")
            return _obj(
                text='<tool_call>{"name": "recall", "arguments": {"query": "x"}}</tool_call>',
                usage_metadata=_obj(prompt_token_count=1, candidates_token_count=2),
            )

    p = GeminiProvider.__new__(GeminiProvider)
    p.model = "gemini-2.5-flash"
    p._api_key = "k"
    p._client = _obj(models=Models())
    GeminiProvider._NO_NATIVE_TOOLS = set()

    resp = p.complete([Message(role="user", content="hi")], tools=[SPEC])
    assert attempts == [True, False]
    assert resp.tool_calls[0].name == "recall"


def test_anthropic_falls_back_to_prompted_mode():
    from tawn.model.providers.anthropic import AnthropicProvider

    attempts = []

    class Messages:
        def create(self, **kw):
            attempts.append("tools" in kw)
            if "tools" in kw:
                raise RuntimeError("tools: unsupported for this model")
            return _obj(
                content=[_obj(
                    type="text",
                    text='<tool_call>{"name": "recall", "arguments": {"query": "x"}}</tool_call>',
                )],
                usage=_obj(input_tokens=1, output_tokens=2),
            )

    p = AnthropicProvider.__new__(AnthropicProvider)
    p.model = "claude-opus-4-8"
    p._api_key = "k"
    p._client = _obj(messages=Messages())
    AnthropicProvider._NO_NATIVE_TOOLS = set()

    resp = p.complete([Message(role="user", content="hi")], tools=[SPEC])
    assert attempts == [True, False]
    assert resp.tool_calls[0].name == "recall"


# ── vision: images must actually reach each provider ─────────────────────────

IMG = Message(role="user", content="transcribe",
              images=[{"media_type": "image/png", "data": "QUJD"}])


def test_anthropic_sends_images_as_content_blocks():
    from tawn.model.providers.anthropic import AnthropicProvider

    p = AnthropicProvider.__new__(AnthropicProvider)
    _system, messages = p._split([IMG])
    blocks = messages[0]["content"]
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["data"] == "QUJD"
    assert blocks[0]["source"]["media_type"] == "image/png"
    assert blocks[-1]["type"] == "text"


def test_openai_sends_images_as_data_uris():
    from tawn.model.providers.openai_compat import _encode

    parts = _encode(IMG)["content"]
    assert parts[0]["type"] == "image_url"
    assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,QUJD")
    assert parts[-1]["type"] == "text"


def test_gemini_sends_images_as_inline_data():
    from tawn.model.providers.gemini import GeminiProvider

    p = GeminiProvider.__new__(GeminiProvider)
    _system, contents = p._split([IMG])
    parts = contents[0]["parts"]
    assert parts[0]["inline_data"]["mime_type"] == "image/png"
    assert parts[0]["inline_data"]["data"] == "QUJD"


def test_a_message_without_images_is_encoded_exactly_as_before():
    """Vision support must not change the shape of ordinary text messages."""
    from tawn.model.providers.anthropic import AnthropicProvider
    from tawn.model.providers.gemini import GeminiProvider
    from tawn.model.providers.openai_compat import _encode

    plain = Message(role="user", content="hello")

    a = AnthropicProvider.__new__(AnthropicProvider)
    assert a._split([plain])[1] == [{"role": "user", "content": "hello"}]

    assert _encode(plain) == {"role": "user", "content": "hello"}

    g = GeminiProvider.__new__(GeminiProvider)
    assert g._split([plain])[1] == [
        {"role": "user", "parts": [{"text": "hello"}]}
    ]


def test_mistral_is_registered_as_a_provider():
    from tawn.model.router import CLOUD_REGISTRY, PROVIDER_MODELS

    assert "mistral" in dict(CLOUD_REGISTRY)
    assert PROVIDER_MODELS["mistral"]


def test_the_mistral_provider_points_at_their_endpoint():
    from tawn.model.providers.openai_compat import MISTRAL_BASE, mistral_provider

    p = mistral_provider("sk-test")
    assert p.name == "mistral"
    assert p.locality == "cloud"
    assert MISTRAL_BASE == "https://api.mistral.ai/v1"


def test_mistral_gets_native_tool_calling_through_the_compat_adapter():
    """It speaks the OpenAI dialect, so it needs no special casing."""
    seen = {}

    def create(**kw):
        seen.update(kw)
        return _choice(tool_calls=[
            _obj(id="t1", function=_obj(name="recall", arguments='{"query":"x"}'))
        ])

    p = _compat(model="mistral-large-latest", create=create)
    p.name = "mistral"
    resp = p.complete([Message(role="user", content="hi")], tools=[SPEC])
    assert seen["tools"][0]["function"]["name"] == "recall"
    assert resp.tool_calls[0].name == "recall"
