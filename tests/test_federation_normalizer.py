"""Tests for federation normalizer."""
import datetime
from pathlib import Path
import pytest
import yaml

from tawn.federation.adapters.base import ConvTurn
from tawn.federation.adapters.claude_code import ClaudeCodeAdapter
from tawn.federation.normalizer import infer_domain, normalise, write_to_raw_imports


def test_normalise_produces_frontmatter():
    turns = [
        ConvTurn(role="user", content="Hello"),
        ConvTurn(role="assistant", content="Hi there"),
    ]
    md = normalise(turns, source="claude-code", domain="work")
    assert md.startswith("---")
    assert "source: claude-code" in md
    assert "domain: work" in md
    assert "type: conversation" in md


def test_normalise_includes_turns():
    turns = [ConvTurn(role="user", content="explain X")]
    md = normalise(turns, source="chatgpt", domain="research")
    assert "explain X" in md
    assert "**user:**" in md


def test_infer_domain_from_metadata():
    turns = [ConvTurn(role="user", content="x", metadata={"domain": "academic"})]
    adapter = ClaudeCodeAdapter()
    assert infer_domain(turns, adapter) == "academic"


def test_infer_domain_adapter_default():
    turns = [ConvTurn(role="user", content="x")]
    adapter = ClaudeCodeAdapter()
    assert infer_domain(turns, adapter) == "work"


def test_infer_domain_fallback():
    from tawn.federation.adapters.generic import GenericAdapter
    turns = [ConvTurn(role="user", content="x")]
    assert infer_domain(turns, GenericAdapter()) == "unknown"


def test_write_to_raw_imports_creates_file(tmp_path):
    home = tmp_path / "tawn"
    (home / "raw" / "imports").mkdir(parents=True)
    path = write_to_raw_imports(home, "claude-code", "# Content\n\nHello")
    assert path.exists()
    assert "claude-code" in str(path)
    assert path.read_text() == "# Content\n\nHello\n\n"


def test_write_to_raw_imports_appends(tmp_path):
    home = tmp_path / "tawn"
    (home / "raw" / "imports").mkdir(parents=True)
    write_to_raw_imports(home, "claude-code", "First")
    write_to_raw_imports(home, "claude-code", "Second")
    text = (home / "raw" / "imports" / "claude-code" /
            f"{datetime.date.today().strftime('%Y-%m-%d')}.md").read_text()
    assert "First" in text
    assert "Second" in text
