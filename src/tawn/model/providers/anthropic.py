"""Anthropic adapter — Claude via the official `anthropic` SDK.

Default model claude-opus-4-8 with adaptive thinking. The SDK client is
injected for tests; the API key is redacted from every error message
(governance §8: secrets never in logs).
"""

from collections.abc import Iterator

import anthropic as anthropic_sdk

from tawn.model.types import ErrorKind, Message, ModelError, ModelResponse, StreamChunk


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
            elif m.images:
                # Vision: image blocks precede the text so the model sees what
                # the instruction refers to before reading the instruction.
                blocks = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.get("media_type", "image/png"),
                            "data": img.get("data", ""),
                        },
                    }
                    for img in m.images
                ]
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                messages.append({"role": m.role, "content": blocks})
            else:
                messages.append({"role": m.role, "content": m.content})
        return system, messages

    def complete(
        self,
        msgs: list[Message],
        model: str | None = None,
        tools: list | None = None,
    ) -> ModelResponse:
        model = model or self.model
        system, messages = self._split(msgs)
        use_tools = bool(tools) and model not in self._NO_NATIVE_TOOLS
        if use_tools:
            # Tool calls and results ride as content blocks here, which the
            # plain text split cannot express.
            from tawn.model.toolwire import anthropic_messages

            messages = anthropic_messages(msgs)
        kwargs: dict = {
            "model": model,
            "max_tokens": 16000,
            "thinking": {"type": "adaptive"},
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system
        if use_tools:
            from tawn.model.toolwire import anthropic_tools

            kwargs["tools"] = anthropic_tools(tools)
        elif tools:
            return self._complete_prompted(msgs, model, tools, system)
        try:
            resp = self._client.messages.create(**kwargs)
        except Exception as exc:
            if use_tools and _is_unsupported_tools_error(exc):
                self._NO_NATIVE_TOOLS.add(model)
                return self._complete_prompted(msgs, model, tools, system)
            raise ModelError(
                self._redact(f"anthropic: {exc}"),
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc
        text = "".join(b.text for b in resp.content if b.type == "text")
        usage = getattr(resp, "usage", None)
        tool_calls = []
        if use_tools:
            from tawn.model.toolwire import anthropic_calls

            tool_calls = anthropic_calls(resp)
        return ModelResponse(
            text=text,
            model=model,
            provider=self.name,
            tokens_in=getattr(usage, "input_tokens", 0) or 0,
            tokens_out=getattr(usage, "output_tokens", 0) or 0,
            tool_calls=tool_calls,
        )

    #: Models whose endpoint rejected the tools API, so the next call uses the
    #: prompted protocol directly.
    _NO_NATIVE_TOOLS: set[str] = set()

    def _complete_prompted(
        self, msgs: list[Message], model: str, tools: list, system: str | None
    ) -> ModelResponse:
        """Tools described in the prompt, for a model with no tools API."""
        from tawn.model.prompted import inject_tools, parse_prompted_calls

        prepared = inject_tools(msgs, tools)
        sys_text, messages = self._split(prepared)
        kwargs: dict = {
            "model": model,
            "max_tokens": 16000,
            "thinking": {"type": "adaptive"},
            "messages": messages,
        }
        if sys_text is not None:
            kwargs["system"] = sys_text
        try:
            resp = self._client.messages.create(**kwargs)
        except Exception as exc:
            raise ModelError(
                self._redact(f"anthropic: {exc}"),
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc
        raw = "".join(b.text for b in resp.content if b.type == "text")
        calls, cleaned = parse_prompted_calls(raw)
        usage = getattr(resp, "usage", None)
        return ModelResponse(
            text=cleaned,
            model=model,
            provider=self.name,
            tokens_in=getattr(usage, "input_tokens", 0) or 0,
            tokens_out=getattr(usage, "output_tokens", 0) or 0,
            tool_calls=calls,
        )

    def stream_complete(self, msgs: list[Message], model: str | None = None) -> Iterator[StreamChunk]:
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
            with self._client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield StreamChunk(text=text)
                final = stream.get_final_message()
                usage = getattr(final, "usage", None)
                yield StreamChunk(
                    text="",
                    done=True,
                    tokens_in=getattr(usage, "input_tokens", 0) or 0,
                    tokens_out=getattr(usage, "output_tokens", 0) or 0,
                )
        except Exception as exc:
            raise ModelError(
                self._redact(f"anthropic: {exc}"),
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc

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


def _is_unsupported_tools_error(exc: Exception) -> bool:
    """Whether the endpoint rejected the *tools API* rather than the request."""
    text = str(exc).lower()
    return "tool" in text and any(
        phrase in text
        for phrase in (
            "does not support", "not supported", "unsupported",
            "unrecognized", "unknown parameter", "invalid",
        )
    )
