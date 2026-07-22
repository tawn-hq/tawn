"""Tests for all six built-in federation adapters."""
import json
from pathlib import Path
import pytest

from tawn.federation.adapters.claude_ai import ClaudeAIAdapter
from tawn.federation.adapters.chatgpt import ChatGPTAdapter
from tawn.federation.adapters.gemini import GeminiAdapter
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

CODEX_LINES = [
    json.dumps({"role": "user", "content": "refactor this"}),
    json.dumps({"role": "assistant", "content": "Here is the refactor"}),
]


def test_codex_can_handle(tmp_path):
    f = tmp_path / "session-abc123.jsonl"
    f.write_text("\n".join(CODEX_LINES))
    assert CodexAdapter().can_handle(f)


def test_codex_parse(tmp_path):
    f = tmp_path / "session-abc123.jsonl"
    f.write_text("\n".join(CODEX_LINES))
    turns = CodexAdapter().parse(f)
    assert len(turns) == 2
    assert turns[1].role == "assistant"


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
