"""Provider-neutral model types (design spec §15.1–15.2).

The router never touches a vendor SDK; adapters translate to/from
these shapes and normalize vendor errors into ErrorKind.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    """A callable the model may invoke, whatever its origin.

    MCP servers, Tawn's own verbs and generated tools all reduce to this, so
    the agent loop has one code path and the audit log one shape.
    """

    name: str
    description: str
    parameters: dict  # JSON Schema
    #: "mcp:<server>" | "tawn" | "tawn:manage" | "local:<tool>"
    source: str = "tawn"
    #: read | write | net | shell — checked against grants before execution.
    capabilities: list[str] = Field(default_factory=list)
    #: True when this tool returns content Tawn did not author — web pages,
    #: third-party MCP results, files from outside its own store. Whatever it
    #: returns must be treated as data, never as instruction.
    returns_untrusted: bool = False
    #: True when calling this tool changes something outside the conversation.
    #: These are withdrawn once untrusted content has entered a turn.
    side_effecting: bool = False


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    id: str
    content: str
    is_error: bool = False


class ToolsUnsupported(Exception):
    """Raised when tools are passed to a model that cannot call them.

    Never swallowed: a model that silently ignores its tools answers
    confidently from nothing, which is the worst outcome and the hardest to
    notice.
    """

    def __init__(self, model: str, provider: str = ""):
        super().__init__(f"{provider or 'provider'} model '{model}' cannot call tools")
        self.model = model
        self.provider = provider


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    #: Set on assistant messages that requested tools.
    tool_calls: list[ToolCall] = Field(default_factory=list)
    #: Set on tool messages, linking the result back to its call.
    tool_call_id: str | None = None
    #: Base64 images for vision models: [{"media_type": ..., "data": ...}].
    #: Providers that cannot see them ignore the field and read `content`,
    #: which is a degraded answer rather than a crash.
    images: list[dict] = Field(default_factory=list)


class ModelResponse(BaseModel):
    text: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    #: Non-empty when the model asked to call tools instead of answering.
    tool_calls: list[ToolCall] = Field(default_factory=list)


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
