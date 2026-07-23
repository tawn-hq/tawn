"""Adapter for OpenAI Codex CLI session files (~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl).

Each line is an envelope: {"timestamp": ..., "type": "session_meta" |
"event_msg" | "response_item" | "turn_context", "payload": {...}}.
Conversation turns live in "response_item" lines whose payload is itself
an OpenAI-Responses-API-shaped message: {"type": "message", "role": ...,
"content": [{"type": "input_text" | "output_text" | ..., "text": ...}]}.
"role": "developer" lines are Codex's injected system/tool instructions,
not user or assistant turns — skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

from tawn.federation.adapters.base import BaseAdapter, ConvTurn


class CodexAdapter(BaseAdapter):
    name = "codex"
    default_domain = "work"
    DETECT_PATHS = ["~/.codex/sessions/"]
    DETECT_BINS = ["codex"]

    def can_handle(self, path: Path) -> bool:
        if path.suffix != ".jsonl":
            return False
        if not path.stem.startswith("rollout-"):
            return False
        try:
            for line in path.read_text(errors="replace").splitlines()[:5]:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("type") in ("session_meta", "event_msg", "response_item", "turn_context"):
                    return True
            return False
        except Exception:
            return False

    def parse(self, path: Path) -> list[ConvTurn]:
        turns: list[ConvTurn] = []
        try:
            for line in path.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "response_item":
                    continue
                payload = obj.get("payload", {})
                if payload.get("type") != "message":
                    continue
                role = payload.get("role", "")
                if role not in ("user", "assistant"):
                    continue
                blocks = payload.get("content", [])
                text = " ".join(
                    b.get("text", "") for b in blocks
                    if isinstance(b, dict) and b.get("text")
                ).strip()
                if text:
                    turns.append(ConvTurn(role=role, content=text, source=self.name))
        except Exception:
            return []
        return turns
