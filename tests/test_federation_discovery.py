"""Tests for federation discovery."""
from pathlib import Path
import pytest
from tawn.federation.config import load_config, save_config, FedSource
from tawn.federation.discovery import discover, run_discovery


def test_discover_known_path(tmp_path):
    fake_claude = tmp_path / ".claude" / "projects"
    fake_claude.mkdir(parents=True)
    sources = discover(
        home=tmp_path / "tawn",
        detect_paths_override={"claude-code": str(fake_claude.parent)},
    )
    names = [s.name for s in sources]
    assert "claude-code" in names


def test_discover_skips_already_configured(tmp_path):
    home = tmp_path / "tawn"
    (home / "federation" / "adapters").mkdir(parents=True)
    existing = FedSource(name="claude-code", path="~/.claude/",
                         adapter="claude_code", auto_detected=True)
    save_config(home, [existing])
    sources = discover(
        home=home,
        detect_paths_override={"claude-code": str(tmp_path / ".claude")},
    )
    assert not any(s.name == "claude-code" for s in sources)


def test_run_discovery_adds_to_config(tmp_path):
    home = tmp_path / "tawn"
    (home / "federation" / "adapters").mkdir(parents=True)
    fake_claude = tmp_path / "dot_claude" / "projects"
    fake_claude.mkdir(parents=True)
    added = run_discovery(
        home=home,
        detect_paths_override={"claude-code": str(fake_claude.parent)},
    )
    assert added >= 1
    sources = load_config(home)
    assert any(s.name == "claude-code" for s in sources)


def test_run_discovery_no_tools(tmp_path):
    home = tmp_path / "tawn"
    (home / "federation" / "adapters").mkdir(parents=True)
    added = run_discovery(home=home, detect_paths_override={})
    assert added == 0
