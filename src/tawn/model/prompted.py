"""Prompted tool calling — the universal fallback.

Not every model exposes a tools API. Small local models, older checkpoints and
some OpenAI-compatible endpoints do not, and refusing to let those models use
tools at all would mean Tawn's whole tool surface only worked on the expensive
providers — exactly backwards for a local-first system.

So there is a ladder:

    native    the provider has a tools API      → structured, reliable
    prompted  no tools API                      → describe the tools in the
                                                  prompt, parse a JSON block
    none      explicitly disabled

Prompted mode is less reliable than native — a model can ignore the protocol or
emit malformed JSON — so it is used only where native is unavailable, and its
parser is deliberately forgiving about surrounding prose while strict about the
JSON itself.
"""

from __future__ import annotations

import json
import re

from tawn.model.types import Message, ToolCall, ToolSpec

TOOL_TAG = "tool_call"

_BLOCK = re.compile(rf"<{TOOL_TAG}>\s*(.*?)\s*</{TOOL_TAG}>", re.S)
#: Some models emit a fenced block instead of the tag. Accepted too, because
#: refusing a well-formed intent over its wrapper helps nobody.
_FENCED = re.compile(r"```(?:json)?\s*(\{[^`]*?\"name\"[^`]*?\})\s*```", re.S)


def prompted_system_block(specs: list[ToolSpec]) -> str:
    """The instructions that teach a model without a tools API how to call one."""
    lines = [
        "You have access to tools. To call one, emit a block in exactly this form:",
        "",
        f"<{TOOL_TAG}>",
        '{"name": "tool_name", "arguments": {"arg": "value"}}',
        f"</{TOOL_TAG}>",
        "",
        "Rules:",
        "- Emit the block and nothing else when you want to call a tool.",
        "- You may emit several blocks to call several tools at once.",
        "- Wait for the result before drawing conclusions; do not invent results.",
        "- When you have enough information, answer normally with no block.",
        "",
        "Available tools:",
        "",
    ]
    for s in specs:
        props = (s.parameters or {}).get("properties") or {}
        required = set((s.parameters or {}).get("required") or [])
        args = ", ".join(
            f"{k}{'' if k in required else '?'}: {(v or {}).get('type', 'any')}"
            for k, v in props.items()
        )
        lines.append(f"- {s.name}({args})")
        if s.description:
            lines.append(f"    {s.description}")
    return "\n".join(lines)


def parse_prompted_calls(text: str) -> tuple[list[ToolCall], str]:
    """Extract tool calls from a model's prose. Returns (calls, remaining text)."""
    if not text:
        return [], ""
    calls: list[ToolCall] = []
    seen_spans: list[tuple[int, int]] = []

    for pattern in (_BLOCK, _FENCED):
        for m in pattern.finditer(text):
            payload = m.group(1).strip()
            try:
                data = json.loads(payload)
            except Exception:
                continue
            if not isinstance(data, dict) or not data.get("name"):
                continue
            args = data.get("arguments") or data.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            calls.append(
                ToolCall(
                    id=f"prompted-{len(calls)}",
                    name=str(data["name"]),
                    arguments=args,
                )
            )
            seen_spans.append(m.span())

    cleaned = text
    for start, end in sorted(seen_spans, reverse=True):
        cleaned = cleaned[:start] + cleaned[end:]
    return calls, cleaned.strip()


def inject_tools(msgs: list[Message], specs: list[ToolSpec]) -> list[Message]:
    """Return a copy of the conversation with tool instructions in the system
    turn, and tool results rendered as readable text.

    Tool results become plain user turns because a model with no tools API also
    has no `tool` role — sending one would be rejected or silently mangled.
    """
    block = prompted_system_block(specs)
    out: list[Message] = []
    injected = False

    for m in msgs:
        if m.role == "system" and not injected:
            out.append(Message(role="system", content=f"{m.content}\n\n{block}"))
            injected = True
        elif m.role == "tool":
            out.append(
                Message(role="user", content=f"Tool result:\n{m.content}")
            )
        elif m.role == "assistant" and m.tool_calls:
            rendered = "\n".join(
                f"<{TOOL_TAG}>"
                f'{{"name": "{c.name}", "arguments": {json.dumps(c.arguments or {})}}}'
                f"</{TOOL_TAG}>"
                for c in m.tool_calls
            )
            out.append(
                Message(
                    role="assistant",
                    content=f"{m.content}\n{rendered}".strip(),
                )
            )
        else:
            out.append(Message(role=m.role, content=m.content))

    if not injected:
        out.insert(0, Message(role="system", content=block))
    return out
