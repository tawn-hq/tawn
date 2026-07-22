"""Federation dispatcher — routes a file path to the correct adapter."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tawn.federation.adapters.base import BaseAdapter
from tawn.federation.adapters.claude_ai import ClaudeAIAdapter
from tawn.federation.adapters.chatgpt import ChatGPTAdapter
from tawn.federation.adapters.gemini import GeminiAdapter
from tawn.federation.adapters.claude_code import ClaudeCodeAdapter
from tawn.federation.adapters.codex import CodexAdapter
from tawn.federation.adapters.generic import GenericAdapter

# Order matters: specific adapters before generic fallback
ADAPTER_CHAIN: list[BaseAdapter] = [
    ClaudeAIAdapter(),
    ChatGPTAdapter(),
    GeminiAdapter(),
    ClaudeCodeAdapter(),
    CodexAdapter(),
    GenericAdapter(),
]


def dispatch(path: Path) -> BaseAdapter | None:
    """Return the first adapter that can handle path, or None."""
    for adapter in ADAPTER_CHAIN:
        try:
            if adapter.can_handle(path):
                return adapter
        except Exception:
            continue
    return None


def fingerprint(path: Path) -> str:
    """sha256[:16] of file bytes — stable identity for dedup."""
    h = hashlib.sha256(path.read_bytes())
    return h.hexdigest()[:16]
