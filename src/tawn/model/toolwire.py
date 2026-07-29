"""Translating tools to and from each vendor's wire format.

Kept out of the adapters so the shape of a tool call is described once. Each
vendor disagrees about where tool results live (a message role, a content
block, a function-response part) and about what a tool is called
(`tools`/`functions`/`function_declarations`), and none of that should leak
into `agent.py`.
"""

from __future__ import annotations

import json

from tawn.model.types import Message, ToolCall, ToolSpec

#: Vendors reject unknown JSON-Schema keys, so specs are pruned to the subset
#: every one of them accepts.
_SCHEMA_KEYS = ("type", "properties", "required", "items", "enum", "description")


def _clean_schema(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    out = {k: v for k, v in schema.items() if k in _SCHEMA_KEYS}
    out.setdefault("type", "object")
    if out["type"] == "object":
        props = out.get("properties") or {}
        out["properties"] = {
            k: _clean_schema(v) if isinstance(v, dict) else v for k, v in props.items()
        }
    return out


# ── Anthropic ────────────────────────────────────────────────────────────────

def anthropic_tools(specs: list[ToolSpec]) -> list[dict]:
    return [
        {
            "name": s.name,
            "description": s.description,
            "input_schema": _clean_schema(s.parameters),
        }
        for s in specs
    ]


def anthropic_messages(msgs: list[Message]) -> list[dict]:
    """Anthropic carries tool calls and results as content blocks."""
    out: list[dict] = []
    for m in msgs:
        if m.role == "system":
            continue
        if m.role == "tool":
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_call_id or "",
                            "content": m.content,
                        }
                    ],
                }
            )
        elif m.role == "assistant" and m.tool_calls:
            blocks: list[dict] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for c in m.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                )
            out.append({"role": "assistant", "content": blocks})
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def anthropic_calls(resp) -> list[ToolCall]:
    calls = []
    for block in getattr(resp, "content", None) or []:
        if getattr(block, "type", None) == "tool_use":
            calls.append(
                ToolCall(
                    id=getattr(block, "id", "") or "",
                    name=getattr(block, "name", "") or "",
                    arguments=dict(getattr(block, "input", None) or {}),
                )
            )
    return calls


# ── OpenAI-compatible ────────────────────────────────────────────────────────

def openai_tools(specs: list[ToolSpec]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": _clean_schema(s.parameters),
            },
        }
        for s in specs
    ]


def openai_messages(msgs: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in msgs:
        if m.role == "tool":
            out.append(
                {"role": "tool", "tool_call_id": m.tool_call_id or "", "content": m.content}
            )
        elif m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments or {}),
                            },
                        }
                        for c in m.tool_calls
                    ],
                }
            )
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def openai_calls(resp) -> list[ToolCall]:
    try:
        raw = resp.choices[0].message.tool_calls or []
    except Exception:
        return []
    calls = []
    for c in raw:
        fn = getattr(c, "function", None)
        args = getattr(fn, "arguments", "") or "{}"
        try:
            parsed = json.loads(args) if isinstance(args, str) else dict(args)
        except Exception:
            # A model can emit malformed JSON. An empty dict lets the tool
            # report a clear argument error rather than the turn dying here.
            parsed = {}
        calls.append(
            ToolCall(id=getattr(c, "id", "") or "", name=getattr(fn, "name", "") or "",
                     arguments=parsed)
        )
    return calls


# ── Gemini ───────────────────────────────────────────────────────────────────

def gemini_tools(specs: list[ToolSpec]) -> list[dict]:
    return [
        {
            "function_declarations": [
                {
                    "name": s.name,
                    "description": s.description,
                    "parameters": _clean_schema(s.parameters),
                }
                for s in specs
            ]
        }
    ]


def gemini_calls(resp) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for i, cand in enumerate(getattr(resp, "candidates", None) or []):
        content = getattr(cand, "content", None)
        for j, part in enumerate(getattr(content, "parts", None) or []):
            fn = getattr(part, "function_call", None)
            if fn is None:
                continue
            calls.append(
                ToolCall(
                    # Gemini does not issue call ids, but the loop needs one to
                    # pair a result with its call.
                    id=f"gemini-{i}-{j}",
                    name=getattr(fn, "name", "") or "",
                    arguments=dict(getattr(fn, "args", None) or {}),
                )
            )
    return calls


def gemini_parts(msgs: list[Message]) -> list[dict]:
    """Gemini turns: user/model roles, with tool results as function responses."""
    out: list[dict] = []
    for m in msgs:
        if m.role == "system":
            continue
        if m.role == "tool":
            out.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": m.tool_call_id or "tool",
                                "response": {"result": m.content},
                            }
                        }
                    ],
                }
            )
        elif m.role == "assistant" and m.tool_calls:
            parts: list[dict] = []
            if m.content:
                parts.append({"text": m.content})
            for c in m.tool_calls:
                parts.append({"function_call": {"name": c.name, "args": c.arguments}})
            out.append({"role": "model", "parts": parts})
        else:
            role = "model" if m.role == "assistant" else "user"
            out.append({"role": role, "parts": [{"text": m.content}]})
    return out
