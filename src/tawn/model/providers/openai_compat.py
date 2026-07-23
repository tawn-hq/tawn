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

    def complete(self, msgs: list[Message], model: str | None = None) -> ModelResponse:
        model = model or self.model
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=[{"role": m.role, "content": m.content} for m in msgs],
            )
        except Exception as exc:
            raise ModelError(
                self._redact(f"{self.name}: {exc}"),
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc
        usage = getattr(resp, "usage", None)
        return ModelResponse(
            text=resp.choices[0].message.content or "",
            model=model,
            provider=self.name,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
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
