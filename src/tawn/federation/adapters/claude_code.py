"""Adapter for Claude Code (~/.claude/projects/) JSONL sessions."""

from __future__ import annotations

import json
from pathlib import Path

from tawn.federation.adapters.base import BaseAdapter, ConvTurn


class ClaudeCodeAdapter(BaseAdapter):
    name = "claude-code"
    default_domain = "work"
    DETECT_PATHS = ["~/.claude/projects/"]
    DETECT_BINS = ["claude"]

    def can_handle(self, path: Path) -> bool:
        if path.suffix != ".jsonl":
            return False
        try:
            for line in path.read_text(errors="replace").splitlines()[:10]:
                if not line.strip():
                    continue
                obj = json.loads(line)
                # Claude Code format: {"type":"user"|"assistant", "message":{...}}
                if obj.get("type") in ("user", "assistant") and "message" in obj:
                    return True
                # Also accept older format with top-level role
                if "role" in obj:
                    return True
        except Exception:
            pass
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

                # Claude Code envelope format: {"type":"user"|"assistant","message":{...}}
                msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
                if msg is not None:
                    role = msg.get("role", "")
                else:
                    # Fallback: flat format {"role":"...","content":"..."}
                    role = obj.get("role", "")
                    msg = obj

                if role not in ("user", "assistant"):
                    continue

                content = msg.get("content", "")
                if isinstance(content, list):
                    # content blocks: [{type:text, text:...}, {type:tool_use,...}]
                    parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                parts.append(block.get("text", ""))
                            elif block.get("type") == "tool_result":
                                # tool results can carry useful context
                                inner = block.get("content", "")
                                if isinstance(inner, list):
                                    parts += [b.get("text", "") for b in inner if isinstance(b, dict) and b.get("type") == "text"]
                                elif isinstance(inner, str):
                                    parts.append(inner)
                        elif isinstance(block, str):
                            parts.append(block)
                    content = " ".join(p for p in parts if p).strip()
                else:
                    content = str(content).strip()

                if content:
                    turns.append(ConvTurn(role=role, content=content, source=self.name))
        except Exception:
            return []
        return turns
