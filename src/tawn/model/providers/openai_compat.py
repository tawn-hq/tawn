"""OpenAI-compatible adapter — covers OpenAI itself and every provider that
speaks its chat-completions dialect (DeepSeek today; Groq/Mistral/xAI later:
one factory function each, no new adapter class).
"""

import openai as openai_sdk

from tawn.model.types import ErrorKind, Message, ModelError, ModelResponse

DEEPSEEK_BASE = "https://api.deepseek.com"


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
