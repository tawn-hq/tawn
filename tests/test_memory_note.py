"""Tests for note() verb (Task 11)."""

import datetime
import os
from pathlib import Path

import pytest

from tawn.memory.note import note


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "tawn"
    (h / "raw" / "agent-notes").mkdir(parents=True)
    os.environ["TAWN_HOME"] = str(h)
    yield h
    del os.environ["TAWN_HOME"]


def test_note_creates_daily_file(home):
    result = note("Decided to use pgvector.", home=home)
    assert result["ok"] is True
    today = datetime.date.today().strftime("%Y-%m-%d")
    expected = home / "raw" / "agent-notes" / f"{today}.md"
    assert expected.exists()


def test_note_appends_to_existing_file(home):
    note("First note.", home=home)
    note("Second note.", home=home)
    today = datetime.date.today().strftime("%Y-%m-%d")
    text = (home / "raw" / "agent-notes" / f"{today}.md").read_text()
    assert "First note." in text
    assert "Second note." in text


def test_note_writes_frontmatter(home):
    note("Decision note.", domain="work", type="decision",
         confidence="high", source="claude-code", ttl_days=90, home=home)
    today = datetime.date.today().strftime("%Y-%m-%d")
    text = (home / "raw" / "agent-notes" / f"{today}.md").read_text()
    assert "type: decision" in text
    assert "domain: work" in text
    assert "confidence: high" in text
    assert "ttl_days: 90" in text


def test_note_queues_compile(home):
    note("Something.", home=home)
    assert (home / ".compile-requested").exists()


def test_note_rejects_empty_payload(home):
    with pytest.raises(ValueError, match="empty"):
        note("", home=home)


def test_note_rejects_whitespace_only(home):
    with pytest.raises(ValueError, match="empty"):
        note("   ", home=home)


def test_note_returns_path(home):
    result = note("Test note.", home=home)
    assert "path" in result
    assert "agent-notes" in result["path"]


def test_note_returns_compile_queued(home):
    result = note("Test note.", home=home)
    assert result["compile_queued"] is True


def test_note_default_type_is_observation(home):
    today = datetime.date.today().strftime("%Y-%m-%d")
    note("Some observation.", home=home)
    text = (home / "raw" / "agent-notes" / f"{today}.md").read_text()
    assert "type: observation" in text
