"""Gemini adapter — first cloud tier, via the official google-genai SDK.

The SDK client is injected for tests; the API key lives only inside it and is
redacted from every error message (governance §8: secrets never in logs).
"""

from collections.abc import Iterator

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from tawn.model.types import ErrorKind, Message, ModelError, ModelResponse, StreamChunk


class GeminiProvider:
    name = "gemini"
    locality = "cloud"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        client: genai.Client | None = None,
    ):
        self._api_key = api_key
        self.model = model
        self._client = client or genai.Client(api_key=api_key)

    def _split(self, msgs: list[Message]) -> tuple[str | None, list[dict]]:
        """system → system_instruction; user/assistant → content turns."""
        system: str | None = None
        contents: list[dict] = []
        for m in msgs:
            if m.role == "system":
                system = m.content if system is None else f"{system}\n{m.content}"
            else:
                role = "model" if m.role == "assistant" else "user"
                parts: list[dict] = [
                    {
                        "inline_data": {
                            "mime_type": img.get("media_type", "image/png"),
                            "data": img.get("data", ""),
                        }
                    }
                    for img in getattr(m, "images", None) or []
                ]
                if m.content or not parts:
                    parts.append({"text": m.content})
                contents.append({"role": role, "parts": parts})
        return system, contents

    def complete(
        self,
        msgs: list[Message],
        model: str | None = None,
        tools: list | None = None,
    ) -> ModelResponse:
        model = model or self.model
        system, contents = self._split(msgs)
        use_tools = bool(tools) and model not in self._NO_NATIVE_TOOLS
        if use_tools:
            from tawn.model.toolwire import gemini_parts, gemini_tools

            contents = gemini_parts(msgs)
            config = genai_types.GenerateContentConfig(
                system_instruction=system, tools=gemini_tools(tools)
            )
        elif tools:
            return self._complete_prompted(msgs, model, tools)
        else:
            config = genai_types.GenerateContentConfig(system_instruction=system)
        try:
            resp = self._client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as exc:
            if use_tools and _is_unsupported_tools_error(exc):
                self._NO_NATIVE_TOOLS.add(model)
                return self._complete_prompted(msgs, model, tools)
            raise ModelError(
                self._redact(f"gemini: {exc}"),
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc
        usage = getattr(resp, "usage_metadata", None)
        tool_calls = []
        if use_tools:
            from tawn.model.toolwire import gemini_calls

            tool_calls = gemini_calls(resp)
        # `resp.text` raises on a candidate that is purely a function call.
        try:
            text = resp.text or ""
        except Exception:
            text = ""
        return ModelResponse(
            text=text,
            model=model,
            provider=self.name,
            tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) or 0,
            tool_calls=tool_calls,
        )

    #: Models whose endpoint rejected the tools API, so the next call uses the
    #: prompted protocol directly.
    _NO_NATIVE_TOOLS: set[str] = set()

    def _complete_prompted(
        self, msgs: list[Message], model: str, tools: list
    ) -> ModelResponse:
        """Tools described in the prompt, for a model with no tools API."""
        from tawn.model.prompted import inject_tools, parse_prompted_calls

        prepared = inject_tools(msgs, tools)
        system, contents = self._split(prepared)
        config = genai_types.GenerateContentConfig(system_instruction=system)
        try:
            resp = self._client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as exc:
            raise ModelError(
                self._redact(f"gemini: {exc}"),
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc
        try:
            raw = resp.text or ""
        except Exception:
            raw = ""
        calls, cleaned = parse_prompted_calls(raw)
        usage = getattr(resp, "usage_metadata", None)
        return ModelResponse(
            text=cleaned,
            model=model,
            provider=self.name,
            tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) or 0,
            tool_calls=calls,
        )

    def stream_complete(self, msgs: list[Message], model: str | None = None) -> Iterator[StreamChunk]:
        model = model or self.model
        system, contents = self._split(msgs)
        config = genai_types.GenerateContentConfig(system_instruction=system)
        try:
            tokens_in = tokens_out = 0
            for chunk in self._client.models.generate_content_stream(model=model, contents=contents, config=config):
                if chunk.text:
                    yield StreamChunk(text=chunk.text)
                usage = getattr(chunk, "usage_metadata", None)
                if usage is not None:
                    tokens_in = usage.prompt_token_count or 0
                    tokens_out = usage.candidates_token_count or 0
            yield StreamChunk(text="", done=True, tokens_in=tokens_in, tokens_out=tokens_out)
        except Exception as exc:
            raise ModelError(
                self._redact(f"gemini: {exc}"),
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc

    def available_models(self) -> list[dict]:
        """Chat-capable models on this key, [] when unreachable.

        Same row shape across providers so `tawn model explore` can merge:
        {name, provider, description, context_tokens, output_tokens}.
        """
        try:
            listing = list(self._client.models.list())
        except Exception:
            return []
        rows = []
        for m in listing:
            if "generateContent" not in (m.supported_actions or []):
                continue
            rows.append(
                {
                    "name": (m.name or "").removeprefix("models/"),
                    "provider": self.name,
                    "description": m.description or "",
                    "context_tokens": m.input_token_limit or 0,
                    "output_tokens": m.output_token_limit or 0,
                }
            )
        return rows

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key, "***")

    def count_tokens(self, msgs: list[Message]) -> int:
        return max(1, sum(len(m.content) for m in msgs) // 4)

    def classify_error(self, exc: Exception) -> ErrorKind:
        if isinstance(exc, httpx.TimeoutException):
            return ErrorKind.TIMEOUT
        if isinstance(exc, httpx.ConnectError):
            return ErrorKind.SERVER_ERROR
        if isinstance(exc, genai_errors.APIError):
            code = exc.code or 0
            status = (exc.status or "").upper()
            message = (exc.message or "").lower()
            if code == 429:
                if "RESOURCE_EXHAUSTED" in status or "quota" in message:
                    return ErrorKind.QUOTA_EXHAUSTED
                return ErrorKind.RATE_LIMIT
            if code == 400 and ("token" in message or "exceeds" in message):
                return ErrorKind.CONTEXT_OVERFLOW
            if code in (401, 403):
                return ErrorKind.AUTH
            if code >= 500:
                return ErrorKind.SERVER_ERROR
            return ErrorKind.UNKNOWN
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
