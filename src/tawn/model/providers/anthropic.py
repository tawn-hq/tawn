"""Anthropic adapter — Claude via the official `anthropic` SDK.

Default model claude-opus-4-8 with adaptive thinking. The SDK client is
injected for tests; the API key is redacted from every error message
(governance §8: secrets never in logs).
"""

import anthropic as anthropic_sdk

from tawn.model.types import ErrorKind, Message, ModelError, ModelResponse


class AnthropicProvider:
    name = "anthropic"
    locality = "cloud"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-4-8",
        client: anthropic_sdk.Anthropic | None = None,
    ):
        self._api_key = api_key
        self.model = model
        self._client = client or anthropic_sdk.Anthropic(api_key=api_key)

    def _split(self, msgs: list[Message]) -> tuple[str | None, list[dict]]:
        """system → the system param; user/assistant → message turns."""
        system: str | None = None
        messages: list[dict] = []
        for m in msgs:
            if m.role == "system":
                system = m.content if system is None else f"{system}\n{m.content}"
            else:
                messages.append({"role": m.role, "content": m.content})
        return system, messages

    def complete(self, msgs: list[Message], model: str | None = None) -> ModelResponse:
        model = model or self.model
        system, messages = self._split(msgs)
        kwargs: dict = {
            "model": model,
            "max_tokens": 16000,
            "thinking": {"type": "adaptive"},
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system
        try:
            resp = self._client.messages.create(**kwargs)
        except Exception as exc:
            raise ModelError(
                self._redact(f"anthropic: {exc}"),
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc
        text = "".join(b.text for b in resp.content if b.type == "text")
        usage = getattr(resp, "usage", None)
        return ModelResponse(
            text=text,
            model=model,
            provider=self.name,
            tokens_in=getattr(usage, "input_tokens", 0) or 0,
            tokens_out=getattr(usage, "output_tokens", 0) or 0,
        )

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key, "***")

    def count_tokens(self, msgs: list[Message]) -> int:
        return max(1, sum(len(m.content) for m in msgs) // 4)

    def classify_error(self, exc: Exception) -> ErrorKind:
        if isinstance(exc, anthropic_sdk.APITimeoutError):
            return ErrorKind.TIMEOUT
        if isinstance(exc, anthropic_sdk.RateLimitError):
            return ErrorKind.RATE_LIMIT
        if isinstance(
            exc, anthropic_sdk.AuthenticationError | anthropic_sdk.PermissionDeniedError
        ):
            return ErrorKind.AUTH
        if isinstance(exc, anthropic_sdk.BadRequestError):
            message = str(exc).lower()
            if "credit" in message or "billing" in message:
                return ErrorKind.QUOTA_EXHAUSTED
            if "too long" in message or "token" in message:
                return ErrorKind.CONTEXT_OVERFLOW
            return ErrorKind.UNKNOWN
        if isinstance(exc, anthropic_sdk.APIStatusError):
            if exc.response.status_code >= 500:
                return ErrorKind.SERVER_ERROR
            return ErrorKind.UNKNOWN
        if isinstance(exc, anthropic_sdk.APIConnectionError):
            return ErrorKind.SERVER_ERROR
        return ErrorKind.UNKNOWN
