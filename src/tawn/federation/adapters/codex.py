"""Adapter for OpenAI Codex CLI session files."""

from __future__ import annotations

import json
from pathlib import Path

from tawn.federation.adapters.base import BaseAdapter, ConvTurn


class CodexAdapter(BaseAdapter):
    name = "codex"
    default_domain = "work"
    DETECT_PATHS = ["~/.codex/"]
    DETECT_BINS = ["codex"]

    def can_handle(self, path: Path) -> bool:
        if path.suffix != ".jsonl":
            return False
        if not path.stem.startswith("session"):
            return False
        try:
            first = path.read_text(errors="replace").splitlines()[0]
            obj = json.loads(first)
            return "role" in obj
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
                role = obj.get("role", "")
                if role not in ("user", "assistant", "system"):
                    continue
                content = str(obj.get("content", "")).strip()
                if content:
                    turns.append(ConvTurn(role=role, content=content, source=self.name))
        except Exception:
            return []
        return turns
