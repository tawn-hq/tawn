"""Ollama adapter — the local tier, via the official `ollama` SDK.

The SDK client is injected for tests. This module also owns local model
management: hardware-aware recommendation, installed inventory, and
streaming pulls, so `tawn model setup` can fit the model to the machine.
"""

from collections.abc import Callable, Iterator

import httpx
import ollama

from tawn.model.types import ErrorKind, Message, ModelError, ModelResponse, StreamChunk

GB = 1024**3

# (min total RAM, model) — a q4 model wants roughly half its parameter count
# in GB free, so recommend one tier below what the box could theoretically fit.
_RAM_LADDER = [
    (48 * GB, "qwen2.5:32b"),
    (24 * GB, "qwen2.5:14b"),
    (12 * GB, "qwen2.5:7b"),
    (6 * GB, "qwen2.5:3b"),
    (0, "qwen2.5:1.5b"),
]


def recommend_model(ram_bytes: int) -> str:
    for floor, model in _RAM_LADDER:
        if ram_bytes >= floor:
            return model
    return _RAM_LADDER[-1][1]


def total_ram_bytes() -> int:
    import os

    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


class OllamaProvider:
    name = "ollama"
    locality = "local"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:7b",
        client: ollama.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = client or ollama.Client(host=self.base_url)

    def complete(self, msgs: list[Message], model: str | None = None) -> ModelResponse:
        model = model or self.model
        messages = [{"role": m.role, "content": m.content} for m in msgs]
        try:
            resp = self._client.chat(model=model, messages=messages)
        except Exception as exc:
            raise ModelError(
                f"ollama: {exc} ({type(exc).__name__})",
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc
        return ModelResponse(
            text=resp.message.content or "",
            model=model,
            provider=self.name,
            tokens_in=resp.prompt_eval_count or 0,
            tokens_out=resp.eval_count or 0,
        )

    def stream_complete(self, msgs: list[Message], model: str | None = None) -> Iterator[StreamChunk]:
        model = model or self.model
        messages = [{"role": m.role, "content": m.content} for m in msgs]
        try:
            for chunk in self._client.chat(model=model, messages=messages, stream=True):
                if chunk.message is not None and chunk.message.content:
                    yield StreamChunk(text=chunk.message.content)
                if chunk.done:
                    yield StreamChunk(
                        text="",
                        done=True,
                        tokens_in=chunk.prompt_eval_count or 0,
                        tokens_out=chunk.eval_count or 0,
                    )
        except Exception as exc:
            raise ModelError(
                f"ollama: {exc} ({type(exc).__name__})",
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc

    def has_model(self, model: str) -> bool:
        """Is the model already pulled locally?"""
        try:
            listing = self._client.list()
        except Exception as exc:
            raise ModelError(
                f"ollama: {exc} ({type(exc).__name__})",
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc
        return model in {m.model for m in listing.models}

    def installed_models(self) -> list[dict]:
        """[{name, size}] of locally pulled models; [] when the daemon is down."""
        try:
            listing = self._client.list()
        except Exception:
            return []
        return [{"name": m.model, "size": m.size} for m in listing.models]

    def pull(
        self, model: str, on_progress: Callable[[dict], None] | None = None
    ) -> None:
        """Download a model via the daemon (streaming progress events)."""
        try:
            for ev in self._client.pull(model, stream=True):
                if on_progress:
                    on_progress(
                        {
                            "status": ev.status,
                            "completed": ev.completed,
                            "total": ev.total,
                        }
                    )
        except Exception as exc:
            raise ModelError(
                f"ollama pull: {exc} ({type(exc).__name__})",
                kind=self.classify_error(exc),
                provider=self.name,
            ) from exc

    def count_tokens(self, msgs: list[Message]) -> int:
        # No tokenizer endpoint worth a round-trip; ~4 chars/token estimate.
        return max(1, sum(len(m.content) for m in msgs) // 4)

    def classify_error(self, exc: Exception) -> ErrorKind:
        if isinstance(exc, httpx.ConnectError | ConnectionError):
            return ErrorKind.SERVER_ERROR  # daemon down/unreachable
        if isinstance(exc, httpx.TimeoutException):
            return ErrorKind.TIMEOUT
        if isinstance(exc, ollama.ResponseError):
            if exc.status_code >= 500:
                return ErrorKind.SERVER_ERROR
            return ErrorKind.UNKNOWN
        return ErrorKind.UNKNOWN
