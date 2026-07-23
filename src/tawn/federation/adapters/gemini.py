"""Adapter for Gemini Takeout JSON export."""

from __future__ import annotations

import json
from pathlib import Path

from tawn.federation.adapters.base import BaseAdapter, ConvTurn


class GeminiAdapter(BaseAdapter):
    name = "gemini"
    default_domain = "unknown"

    def can_handle(self, path: Path) -> bool:
        if path.suffix != ".json":
            return False
        try:
            data = json.loads(path.read_text(errors="replace"))
        except Exception:
            return False
        if not isinstance(data, dict):
            return False
        convs = data.get("conversations", [])
        if not convs:
            return False
        first_turns = convs[0].get("conversation", [])
        return any(t.get("type") in ("human_turn", "model_turn") for t in first_turns)

    def parse(self, path: Path) -> list[ConvTurn]:
        try:
            data = json.loads(path.read_text(errors="replace"))
        except Exception:
            return []
        turns: list[ConvTurn] = []
        for conv in data.get("conversations", []):
            for turn in conv.get("conversation", []):
                t_type = turn.get("type", "")
                role = "user" if t_type == "human_turn" else "assistant"
                parts = turn.get("parts", [])
                text = " ".join(
                    p.get("text", "") for p in parts if isinstance(p, dict)
                ).strip()
                if text:
                    turns.append(ConvTurn(role=role, content=text, source=self.name))
        return turns
