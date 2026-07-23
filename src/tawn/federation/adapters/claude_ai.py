"""Adapter for claude.ai web conversation exports."""

from __future__ import annotations

import json
from pathlib import Path

from tawn.federation.adapters.base import BaseAdapter, ConvTurn


class ClaudeAIAdapter(BaseAdapter):
    name = "claude-ai"
    default_domain = "unknown"
    DETECT_PATHS = []
    DETECT_BINS = []

    def can_handle(self, path: Path) -> bool:
        if path.suffix != ".json":
            return False
        try:
            data = json.loads(path.read_text(errors="replace"))
        except Exception:
            return False
        if not isinstance(data, list) or not data:
            return False
        first = data[0]
        return isinstance(first, dict) and "chat_messages" in first

    def parse(self, path: Path) -> list[ConvTurn]:
        try:
            data = json.loads(path.read_text(errors="replace"))
        except Exception:
            return []
        turns: list[ConvTurn] = []
        for conv in (data if isinstance(data, list) else []):
            for msg in conv.get("chat_messages", []):
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                sender = msg.get("sender", "")
                role = "user" if sender == "human" else "assistant"
                turns.append(ConvTurn(role=role, content=text, source=self.name))
        return turns
