"""Tests for all six built-in federation adapters."""
import json
from pathlib import Path
import pytest

from tawn.federation.adapters.claude_ai import ClaudeAIAdapter
from tawn.federation.adapters.chatgpt import ChatGPTAdapter
from tawn.federation.adapters.gemini import GeminiAdapter
from tawn.federation.adapters.gemini_cli import GeminiCliAdapter
from tawn.federation.adapters.claude_code import ClaudeCodeAdapter
from tawn.federation.adapters.codex import CodexAdapter
from tawn.federation.adapters.generic import GenericAdapter


# ── claude.ai ────────────────────────────────────────────────────────────────

CLAUDE_AI_DATA = [
    {
        "uuid": "abc",
        "name": "Test conv",
        "created_at": "2026-07-01T10:00:00Z",
        "updated_at": "2026-07-01T10:01:00Z",
        "chat_messages": [
            {"uuid": "m1", "text": "Hello", "sender": "human",
             "created_at": "2026-07-01T10:00:00Z"},
            {"uuid": "m2", "text": "Hi there", "sender": "assistant",
             "created_at": "2026-07-01T10:00:01Z"},
        ],
    }
]


def test_claude_ai_can_handle(tmp_path):
    f = tmp_path / "conversations-2026.json"
    f.write_text(json.dumps(CLAUDE_AI_DATA))
    assert ClaudeAIAdapter().can_handle(f)


def test_claude_ai_parse(tmp_path):
    f = tmp_path / "conversations-2026.json"
    f.write_text(json.dumps(CLAUDE_AI_DATA))
    turns = ClaudeAIAdapter().parse(f)
    assert len(turns) == 2
    assert turns[0].role == "user"
    assert turns[0].content == "Hello"
    assert turns[1].role == "assistant"


def test_claude_ai_cannot_handle_other(tmp_path):
    f = tmp_path / "data.json"
    f.write_text(json.dumps({"mapping": {}}))
    assert not ClaudeAIAdapter().can_handle(f)


# ── chatgpt ──────────────────────────────────────────────────────────────────

CHATGPT_DATA = [
    {
        "title": "Test",
        "create_time": 1720000000.0,
        "mapping": {
            "n1": {
                "message": {
                    "author": {"role": "user"},
                    "content": {"parts": ["Hello GPT"]},
                },
                "children": ["n2"],
            },
            "n2": {
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"parts": ["Hello!"]},
                },
                "children": [],
            },
        },
        "current_node": "n2",
    }
]


def test_chatgpt_can_handle(tmp_path):
    f = tmp_path / "conversations.json"
    f.write_text(json.dumps(CHATGPT_DATA))
    assert ChatGPTAdapter().can_handle(f)


def test_chatgpt_parse(tmp_path):
    f = tmp_path / "conversations.json"
    f.write_text(json.dumps(CHATGPT_DATA))
    turns = ChatGPTAdapter().parse(f)
    assert len(turns) >= 2
    roles = {t.role for t in turns}
    assert "user" in roles
    assert "assistant" in roles


# ── gemini ───────────────────────────────────────────────────────────────────

GEMINI_DATA = {
    "conversations": [
        {
            "conversation": [
                {"type": "human_turn", "parts": [{"text": "Hello Gemini"}]},
                {"type": "model_turn", "parts": [{"text": "Hello!"}]},
            ]
        }
    ]
}


def test_gemini_can_handle(tmp_path):
    f = tmp_path / "gemini_export.json"
    f.write_text(json.dumps(GEMINI_DATA))
    assert GeminiAdapter().can_handle(f)


def test_gemini_parse(tmp_path):
    f = tmp_path / "gemini_export.json"
    f.write_text(json.dumps(GEMINI_DATA))
    turns = GeminiAdapter().parse(f)
    assert len(turns) == 2
    assert turns[0].role == "user"
    assert turns[1].role == "assistant"


# ── claude code ──────────────────────────────────────────────────────────────

CLAUDE_CODE_LINES = [
    json.dumps({"role": "user", "content": "explain pgvector",
                "timestamp": "2026-07-01T10:00:00Z"}),
    json.dumps({"role": "assistant", "content": "pgvector is a Postgres extension",
                "timestamp": "2026-07-01T10:00:01Z"}),
]


def test_claude_code_can_handle(tmp_path):
    f = tmp_path / "session.jsonl"
    f.write_text("\n".join(CLAUDE_CODE_LINES))
    assert ClaudeCodeAdapter().can_handle(f)


def test_claude_code_parse(tmp_path):
    f = tmp_path / "session.jsonl"
    f.write_text("\n".join(CLAUDE_CODE_LINES))
    turns = ClaudeCodeAdapter().parse(f)
    assert len(turns) == 2
    assert turns[0].role == "user"
    assert "pgvector" in turns[0].content


# ── codex ────────────────────────────────────────────────────────────────────
# Real ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl envelope: every line is
# {"timestamp":..., "type": "session_meta"|"event_msg"|"response_item"|
# "turn_context", "payload": {...}}. Turns live in response_item lines whose
# payload is an OpenAI-Responses-API message: {"type":"message","role":...,
# "content":[{"type":"input_text"|"output_text","text":...}]}.

CODEX_LINES = [
    json.dumps({
        "timestamp": "2026-07-01T10:00:00Z",
        "type": "session_meta",
        "payload": {"id": "abc123", "cwd": "/home/user/project"},
    }),
    json.dumps({
        "timestamp": "2026-07-01T10:00:01Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "developer",
            "content": [{"type": "input_text", "text": "<permissions instructions>"}],
        },
    }),
    json.dumps({
        "timestamp": "2026-07-01T10:00:02Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "refactor this"}],
        },
    }),
    json.dumps({
        "timestamp": "2026-07-01T10:00:03Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Here is the refactor"}],
        },
    }),
    json.dumps({
        "timestamp": "2026-07-01T10:00:04Z",
        "type": "event_msg",
        "payload": {"type": "task_started", "turn_id": "t1"},
    }),
]


def test_codex_can_handle(tmp_path):
    f = tmp_path / "rollout-2026-07-01T10-00-00-abc123.jsonl"
    f.write_text("\n".join(CODEX_LINES))
    assert CodexAdapter().can_handle(f)


def test_codex_cannot_handle_wrong_filename(tmp_path):
    f = tmp_path / "session-abc123.jsonl"
    f.write_text("\n".join(CODEX_LINES))
    assert not CodexAdapter().can_handle(f)


def test_codex_parse(tmp_path):
    f = tmp_path / "rollout-2026-07-01T10-00-00-abc123.jsonl"
    f.write_text("\n".join(CODEX_LINES))
    turns = CodexAdapter().parse(f)
    # developer role, session_meta, and event_msg lines are all skipped
    assert len(turns) == 2
    assert turns[0].role == "user"
    assert turns[0].content == "refactor this"
    assert turns[1].role == "assistant"
    assert turns[1].content == "Here is the refactor"


# ── gemini cli ───────────────────────────────────────────────────────────────
# Real ~/.gemini/tmp/<project>/logs.json: flat array of
# {"sessionId":..., "messageId": N, "type": "user", "message": "...",
# "timestamp": "..."}. Only "user"-type entries observed in practice.

GEMINI_CLI_DATA = [
    {"sessionId": "s1", "messageId": 0, "type": "user",
     "message": "explain this codebase", "timestamp": "2026-07-01T10:00:00Z"},
    {"sessionId": "s1", "messageId": 1, "type": "user",
     "message": "now add tests", "timestamp": "2026-07-01T10:05:00Z"},
]


def test_gemini_cli_can_handle(tmp_path):
    f = tmp_path / "logs.json"
    f.write_text(json.dumps(GEMINI_CLI_DATA))
    assert GeminiCliAdapter().can_handle(f)


def test_gemini_cli_cannot_handle_wrong_filename(tmp_path):
    f = tmp_path / "other.json"
    f.write_text(json.dumps(GEMINI_CLI_DATA))
    assert not GeminiCliAdapter().can_handle(f)


def test_gemini_cli_parse(tmp_path):
    f = tmp_path / "logs.json"
    f.write_text(json.dumps(GEMINI_CLI_DATA))
    turns = GeminiCliAdapter().parse(f)
    assert len(turns) == 2
    assert all(t.role == "user" for t in turns)
    assert turns[0].content == "explain this codebase"


# ~/.gemini/tmp/<project>/chats/session-*.jsonl — the richer, full-duplex
# transcript (unlike logs.json, which is prompt-only). First line is a
# header; "$set" patch lines and "error"/"info" CLI-noise lines are skipped.

GEMINI_CHAT_LINES = [
    json.dumps({"sessionId": "0aeae984", "projectHash": "abc", "startTime": "2026-07-01T10:00:00Z", "kind": "main"}),
    json.dumps({"id": "e1", "timestamp": "2026-07-01T10:00:01Z", "type": "info", "content": "some CLI notice"}),
    json.dumps({"id": "u1", "timestamp": "2026-07-01T10:00:02Z", "type": "user", "content": [{"text": "explain this codebase"}]}),
    json.dumps({"$set": {"lastUpdated": "2026-07-01T10:00:02Z"}}),
    json.dumps({"id": "g1", "timestamp": "2026-07-01T10:00:05Z", "type": "gemini", "content": "", "model": "gemini-3-flash-preview"}),
    json.dumps({"id": "g2", "timestamp": "2026-07-01T10:00:08Z", "type": "gemini", "content": "Sure — here's the overview.", "model": "gemini-3-flash-preview"}),
]


def test_gemini_cli_can_handle_chat_session(tmp_path):
    d = tmp_path / "myproject" / "chats"
    d.mkdir(parents=True)
    f = d / "session-2026-07-01T10-00-0aeae984.jsonl"
    f.write_text("\n".join(GEMINI_CHAT_LINES))
    assert GeminiCliAdapter().can_handle(f)


def test_gemini_cli_parse_chat_session(tmp_path):
    d = tmp_path / "myproject" / "chats"
    d.mkdir(parents=True)
    f = d / "session-2026-07-01T10-00-0aeae984.jsonl"
    f.write_text("\n".join(GEMINI_CHAT_LINES))
    turns = GeminiCliAdapter().parse(f)
    # info line, $set patch line, and the empty-content gemini turn are skipped
    assert len(turns) == 2
    assert turns[0].role == "user"
    assert turns[0].content == "explain this codebase"
    assert turns[1].role == "assistant"
    assert turns[1].content == "Sure — here's the overview."
    assert turns[1].metadata.get("model") == "gemini-3-flash-preview"


# ── generic ──────────────────────────────────────────────────────────────────

def test_generic_parse_jsonl(tmp_path):
    f = tmp_path / "hermes.jsonl"
    lines = [
        json.dumps({"role": "user", "content": "hello"}),
        json.dumps({"role": "assistant", "content": "hi"}),
    ]
    f.write_text("\n".join(lines))
    turns = GenericAdapter().parse(f)
    assert len(turns) == 2


def test_generic_parse_markdown(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("# Session\n\nSome content here.")
    turns = GenericAdapter().parse(f)
    assert len(turns) == 1
    assert turns[0].role == "user"


def test_generic_returns_empty_on_unreadable(tmp_path):
    f = tmp_path / "corrupt.jsonl"
    f.write_text("not json at all {{{")
    turns = GenericAdapter().parse(f)
    assert turns == []
