"""Adapter for the Gemini CLI's local session data (~/.gemini/tmp/<project>/).

Two real, distinct formats live there:

1. logs.json — flat JSON array per project: [{"sessionId":..., "messageId":
   N, "type": "user", "message": "...", "timestamp": "..."}, ...]. Only
   "user"-type entries have been observed — a prompt log, not a full
   transcript.

2. chats/session-*.jsonl — the actual per-session transcript, one JSON
   object per line. First line is a header ({"sessionId":..., "kind":
   "main", ...}); subsequent lines are either a turn ({"type": "user",
   "content": [{"text": "..."}]} or {"type": "gemini", "content": "...",
   "model": "..."}), an incremental patch ({"$set": {...}}, no "type"),
   or CLI-internal noise ({"type": "error"|"info", ...}) — both skipped.
   This is the richer source (full duplex, carries the model name) and is
   preferred wherever both exist for the same session.
"""

from __future__ import annotations

import json
from pathlib import Path

from tawn.federation.adapters.base import BaseAdapter, ConvTurn


class GeminiCliAdapter(BaseAdapter):
    name = "gemini-cli"
    default_domain = "work"
    DETECT_PATHS = ["~/.gemini/tmp/"]
    DETECT_BINS = ["gemini"]

    def can_handle(self, path: Path) -> bool:
        if path.name == "logs.json":
            try:
                data = json.loads(path.read_text(errors="replace"))
            except Exception:
                return False
            if not isinstance(data, list) or not data:
                return False
            first = data[0]
            return isinstance(first, dict) and "sessionId" in first and "type" in first
        if path.suffix == ".jsonl" and "chats" in path.parts:
            try:
                first_line = path.read_text(errors="replace").splitlines()[0]
                header = json.loads(first_line)
                return "sessionId" in header and "kind" in header
            except Exception:
                return False
        return False

    def parse(self, path: Path) -> list[ConvTurn]:
        if path.name == "logs.json":
            return self._parse_logs_json(path)
        return self._parse_chat_session(path)

    def _parse_logs_json(self, path: Path) -> list[ConvTurn]:
        try:
            data = json.loads(path.read_text(errors="replace"))
        except Exception:
            return []
        turns: list[ConvTurn] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            raw_type = entry.get("type", "")
            role = "user" if raw_type == "user" else "assistant" if raw_type in ("gemini", "model") else None
            if role is None:
                continue
            text = str(entry.get("message", "")).strip()
            if text:
                turns.append(ConvTurn(role=role, content=text, source=self.name))
        return turns

    def _parse_chat_session(self, path: Path) -> list[ConvTurn]:
        turns: list[ConvTurn] = []
        try:
            lines = path.read_text(errors="replace").splitlines()
        except Exception:
            return []
        for line in lines[1:]:  # skip the header line
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "$set" in obj or "type" not in obj:
                continue
            raw_type = obj.get("type")
            if raw_type == "user":
                blocks = obj.get("content", [])
                text = " ".join(
                    b.get("text", "") for b in blocks
                    if isinstance(b, dict) and b.get("text")
                ).strip()
                if text:
                    turns.append(ConvTurn(role="user", content=text, source=self.name))
            elif raw_type == "gemini":
                text = str(obj.get("content", "")).strip()
                if text:
                    turns.append(ConvTurn(
                        role="assistant", content=text, source=self.name,
                        metadata={"model": obj["model"]} if obj.get("model") else {},
                    ))
            # "error" / "info" types are CLI-internal noise, not turns
        return turns
