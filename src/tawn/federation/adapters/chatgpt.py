"""Adapter for ChatGPT conversations.json export."""

from __future__ import annotations

import json
from pathlib import Path

from tawn.federation.adapters.base import BaseAdapter, ConvTurn


class ChatGPTAdapter(BaseAdapter):
    name = "chatgpt"
    default_domain = "unknown"

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
        return isinstance(first, dict) and "mapping" in first and "title" in first

    def parse(self, path: Path) -> list[ConvTurn]:
        try:
            data = json.loads(path.read_text(errors="replace"))
        except Exception:
            return []
        turns: list[ConvTurn] = []
        for conv in (data if isinstance(data, list) else []):
            mapping = conv.get("mapping", {})
            # Walk nodes in BFS order via children links
            seen: set[str] = set()
            # Find root nodes (not referenced as any child)
            all_children: set[str] = set()
            for node in mapping.values():
                all_children.update(node.get("children", []))
            roots = [k for k in mapping if k not in all_children]
            stack = roots[:]
            while stack:
                nid = stack.pop(0)
                if nid in seen:
                    continue
                seen.add(nid)
                node = mapping.get(nid, {})
                msg = node.get("message") or {}
                if msg:
                    role_raw = (msg.get("author") or {}).get("role", "")
                    if role_raw in ("user", "assistant"):
                        parts = (msg.get("content") or {}).get("parts", [])
                        text = " ".join(p for p in parts if isinstance(p, str)).strip()
                        if text:
                            turns.append(ConvTurn(role=role_raw, content=text, source=self.name))
                for child in node.get("children", []):
                    stack.append(child)
        return turns
