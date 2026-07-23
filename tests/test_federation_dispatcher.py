"""Tests for federation dispatcher."""
import json
from pathlib import Path
import pytest
from tawn.federation.dispatcher import dispatch, fingerprint


def test_dispatch_claude_ai(tmp_path):
    data = [{"uuid": "x", "chat_messages": [{"sender": "human", "text": "hi"}]}]
    f = tmp_path / "conversations-2026.json"
    f.write_text(json.dumps(data))
    adapter = dispatch(f)
    assert adapter is not None
    assert adapter.name == "claude-ai"


def test_dispatch_chatgpt(tmp_path):
    data = [{"title": "x", "mapping": {"n1": {"message": {"author": {"role": "user"},
             "content": {"parts": ["hello"]}}, "children": []}}}]
    f = tmp_path / "conversations.json"
    f.write_text(json.dumps(data))
    adapter = dispatch(f)
    assert adapter is not None
    assert adapter.name == "chatgpt"


def test_dispatch_claude_code(tmp_path):
    f = tmp_path / "session.jsonl"
    f.write_text(json.dumps({"role": "user", "content": "hello"}))
    adapter = dispatch(f)
    assert adapter is not None
    assert adapter.name == "claude-code"


def test_dispatch_returns_none_for_unknown(tmp_path):
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG")
    assert dispatch(f) is None


def test_fingerprint_consistent(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("hello")
    fp1 = fingerprint(f)
    fp2 = fingerprint(f)
    assert fp1 == fp2
    assert len(fp1) == 16


def test_fingerprint_changes_with_content(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("hello")
    fp1 = fingerprint(f)
    f.write_text("world")
    fp2 = fingerprint(f)
    assert fp1 != fp2
