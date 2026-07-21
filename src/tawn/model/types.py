"""Provider-neutral model types (design spec §15.1–15.2).

The router never touches a vendor SDK; adapters translate to/from
these shapes and normalize vendor errors into ErrorKind.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ModelResponse(BaseModel):
    text: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class StreamChunk:
    """One increment of a streaming completion. `done=True` marks the
    final chunk, carrying usage (success) or `error` (failure) instead of
    more text."""

    text: str
    done: bool = False
    tokens_in: int | None = None
    tokens_out: int | None = None
    error: str | None = None


class ErrorKind(StrEnum):
    """Spec §15.2 — not all "limits" are equal; the router reacts by kind."""

    RATE_LIMIT = "rate_limit"            # too fast, transient → retry same provider
    QUOTA_EXHAUSTED = "quota_exhausted"  # key spent → switch provider
    CONTEXT_OVERFLOW = "context_overflow"  # too large → compact+handoff (stage 9)
    SERVER_ERROR = "server_error"        # provider unhealthy → break + switch
    TIMEOUT = "timeout"                  # provider unhealthy → break + switch
    AUTH = "auth"                        # bad/missing key → switch, tell user
    UNKNOWN = "unknown"


class ModelError(Exception):
    def __init__(self, message: str, *, kind: ErrorKind, provider: str):
        super().__init__(message)
        self.kind = kind
        self.provider = provider


class Provider(Protocol):
    """The anti-corruption layer. One adapter per vendor implements this."""

    name: str
    locality: Literal["local", "cloud"]

    def complete(self, msgs: list[Message], model: str | None = None) -> ModelResponse: ...

    def stream_complete(self, msgs: list[Message], model: str | None = None) -> Iterator[StreamChunk]: ...

    def count_tokens(self, msgs: list[Message]) -> int: ...

    def classify_error(self, exc: Exception) -> ErrorKind: ...
