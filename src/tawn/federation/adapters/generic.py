"""Fallback adapter for user-registered sources (JSONL or markdown)."""

from __future__ import annotations

import json
from pathlib import Path

from tawn.federation.adapters.base import BaseAdapter, ConvTurn


class GenericAdapter(BaseAdapter):
    name = "generic"
    default_domain = "unknown"

    def can_handle(self, path: Path) -> bool:
        return path.suffix in (".jsonl", ".md", ".txt")

    def parse(self, path: Path) -> list[ConvTurn]:
        if path.suffix == ".jsonl":
            return self._parse_jsonl(path)
        return self._parse_text(path)

    def _parse_jsonl(self, path: Path) -> list[ConvTurn]:
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
                role = obj.get("role", "user")
                content = str(obj.get("content", "")).strip()
                if content:
                    turns.append(ConvTurn(role=role, content=content, source=self.name))
        except Exception:
            return []
        return turns

    def _parse_text(self, path: Path) -> list[ConvTurn]:
        try:
            text = path.read_text(errors="replace").strip()
        except Exception:
            return []
        if not text:
            return []
        return [ConvTurn(role="user", content=text, source=self.name)]
