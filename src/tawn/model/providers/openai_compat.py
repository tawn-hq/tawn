"""OpenAI-compatible adapter — covers OpenAI itself and every provider that
speaks its chat-completions dialect (DeepSeek today; Groq/Mistral/xAI later:
one factory function each, no new adapter class).
"""

from collections.abc import Iterator

import openai as openai_sdk

from tawn.model.types import ErrorKind, Message, ModelError, ModelResponse, StreamChunk

DEEPSEEK_BASE = "https://api.deepseek.com"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
KIMI_BASE = "https://api.moonshot.cn/v1"
QWEN_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
GROQ_BASE = "https://api.groq.com/openai/v1"
GROK_BASE = "https://api.x.ai/v1"
MISTRAL_BASE = "https://api.mistral.ai/v1"


class OpenAICompatProvider:
    locality = "cloud"

    def __init__(
        self,
        name: str,
        api_key: str,
        model: str,
        base_url: str | None = None,
        client: openai_sdk.OpenAI | None = None,
    ):
        self.name = name
        self._api_key = api_key
        self.model = model
        self._client = client or openai_sdk.OpenAI(api_key=api_key, base_url=base_url)

    def complete(
        self,
        msgs: list[Message],
        model: str | None = None,
        tools: list | None = None,
    ) -> ModelResponse:
        model = model or self.model
        use_tools = bool(tools) and model not in self._NO_NATIVE_TOOLS
        kwargs: dict = {"model": model}
        if use_tools:
            from tawn.model.toolwire import openai_messages, openai_tools

            kwargs["messages"] = openai_messages(msgs)
            kwargs["tools"] = openai_tools(tools)
        elif tools:
            # This endpoint has already refused tools once, so go straight to
            # the prompted protocol rather than paying for the rejection again.
            return self._complete_prompted(msgs, model, tools)
        else:
            kwargs["messages"] = [_encode(m) for m in msgs]
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            if use_tools and _is_unsupported_tools_error(exc):
                # Not every OpenAI-compatible endpoint implements tools. Falling
                # back keeps the tool surface working on local gateways instead
                # of restricting it to the expensive providers.
                self._NO_NATIVE_TOOLS.add(model)
                return self._complete_prompted(msgs, model, tools)
            raise ModelError(
                self._redact(f"{self.name}: {exc}"),
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc
        usage = getattr(resp, "usage", None)
        tool_calls = []
        if use_tools:
            from tawn.model.toolwire import openai_calls

            tool_calls = openai_calls(resp)
        return ModelResponse(
            text=resp.choices[0].message.content or "",
            model=model,
            provider=self.name,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            tool_calls=tool_calls,
        )

    #: Models whose endpoint rejected the tools API, so the next call uses the
    #: prompted protocol directly.
    _NO_NATIVE_TOOLS: set[str] = set()

    def _complete_prompted(
        self, msgs: list[Message], model: str, tools: list
    ) -> ModelResponse:
        from tawn.model.prompted import inject_tools, parse_prompted_calls

        prepared = inject_tools(msgs, tools)
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=[{"role": m.role, "content": m.content} for m in prepared],
            )
        except Exception as exc:
            raise ModelError(
                self._redact(f"{self.name}: {exc}"),
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc
        usage = getattr(resp, "usage", None)
        calls, cleaned = parse_prompted_calls(resp.choices[0].message.content or "")
        return ModelResponse(
            text=cleaned,
            model=model,
            provider=self.name,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            tool_calls=calls,
        )

    def stream_complete(self, msgs: list[Message], model: str | None = None) -> Iterator[StreamChunk]:
        model = model or self.model
        try:
            stream = self._client.chat.completions.create(
                model=model,
                messages=[{"role": m.role, "content": m.content} for m in msgs],
                stream=True,
                stream_options={"include_usage": True},
            )
            tokens_in = tokens_out = 0
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is not None and delta.content:
                    yield StreamChunk(text=delta.content)
                if getattr(chunk, "usage", None) is not None:
                    tokens_in = chunk.usage.prompt_tokens or 0
                    tokens_out = chunk.usage.completion_tokens or 0
            yield StreamChunk(text="", done=True, tokens_in=tokens_in, tokens_out=tokens_out)
        except Exception as exc:
            raise ModelError(
                self._redact(f"{self.name}: {exc}"),
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key, "***")

    def count_tokens(self, msgs: list[Message]) -> int:
        return max(1, sum(len(m.content) for m in msgs) // 4)

    def classify_error(self, exc: Exception) -> ErrorKind:
        if isinstance(exc, openai_sdk.APITimeoutError):
            return ErrorKind.TIMEOUT
        if isinstance(exc, openai_sdk.RateLimitError):
            if "insufficient_quota" in str(exc) or "quota" in str(exc).lower():
                return ErrorKind.QUOTA_EXHAUSTED
            return ErrorKind.RATE_LIMIT
        if isinstance(
            exc, openai_sdk.AuthenticationError | openai_sdk.PermissionDeniedError
        ):
            return ErrorKind.AUTH
        if isinstance(exc, openai_sdk.BadRequestError):
            message = str(exc).lower()
            if "context_length" in message or "token" in message:
                return ErrorKind.CONTEXT_OVERFLOW
            return ErrorKind.UNKNOWN
        if isinstance(exc, openai_sdk.APIStatusError):
            if exc.response.status_code >= 500:
                return ErrorKind.SERVER_ERROR
            return ErrorKind.UNKNOWN
        if isinstance(exc, openai_sdk.APIConnectionError):
            return ErrorKind.SERVER_ERROR
        return ErrorKind.UNKNOWN


def openai_provider(api_key: str) -> OpenAICompatProvider:
    return OpenAICompatProvider(name="openai", api_key=api_key, model="gpt-5.1")


def deepseek_provider(api_key: str) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        name="deepseek", api_key=api_key, model="deepseek-chat", base_url=DEEPSEEK_BASE
    )


def openrouter_provider(api_key: str) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        name="openrouter", api_key=api_key,
        model="openai/gpt-4o", base_url=OPENROUTER_BASE,
    )


def kimi_provider(api_key: str) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        name="kimi", api_key=api_key,
        model="moonshot-v1-128k", base_url=KIMI_BASE,
    )


def qwen_provider(api_key: str) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        name="qwen", api_key=api_key,
        model="qwen-max", base_url=QWEN_BASE,
    )


def groq_provider(api_key: str) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        name="groq", api_key=api_key,
        model="llama-3.3-70b-versatile", base_url=GROQ_BASE,
    )


def grok_provider(api_key: str) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        name="grok", api_key=api_key,
        model="grok-3", base_url=GROK_BASE,
    )


def _is_unsupported_tools_error(exc: Exception) -> bool:
    """Whether an endpoint rejected the *tools API* rather than the request.

    Matched on the message because OpenAI-compatible gateways return a plain
    400 for this, indistinguishable by status code from any other bad request.
    """
    text = str(exc).lower()
    return "tool" in text and any(
        phrase in text
        for phrase in (
            "does not support", "not supported", "unsupported",
            "unrecognized", "unknown parameter", "invalid",
        )
    )


def _encode(m) -> dict:
    """One message in OpenAI wire form, with images when present."""
    if not getattr(m, "images", None):
        return {"role": m.role, "content": m.content}
    parts: list[dict] = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{img.get('media_type', 'image/png')};base64,{img.get('data', '')}"
            },
        }
        for img in m.images
    ]
    if m.content:
        parts.append({"type": "text", "text": m.content})
    return {"role": m.role, "content": parts}


def mistral_provider(api_key: str) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        name="mistral", api_key=api_key,
        model="mistral-large-latest", base_url=MISTRAL_BASE,
    )
