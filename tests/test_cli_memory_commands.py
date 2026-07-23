"""Tests for CLI memory commands (Task 16)."""

import os
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from tawn.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _home(tmp_path):
    h = tmp_path / "tawn"
    (h / "raw" / "agent-notes").mkdir(parents=True)
    (h / "wiki").mkdir()
    os.environ["TAWN_HOME"] = str(h)
    yield h
    del os.environ["TAWN_HOME"]


def test_tawn_note_command():
    with patch("tawn.cli.note") as mock_note:
        mock_note.return_value = {
            "ok": True,
            "path": "raw/agent-notes/today.md",
            "compile_queued": True,
        }
        result = runner.invoke(app, ["note", "Test fact from CLI."])
    assert result.exit_code == 0
    mock_note.assert_called_once()
    call_kwargs = mock_note.call_args
    payload = (
        call_kwargs[0][0] if call_kwargs[0]
        else call_kwargs[1].get("payload", "")
    )
    assert "Test fact from CLI." in payload


def test_tawn_recall_command():
    with patch("tawn.cli.recall") as mock_recall:
        mock_recall.return_value = {
            "format": "snippets",
            "query": "pgvector",
            "chunks": [{
                "content": "pgvector decision",
                "source": "raw/a.md",
                "domain": "work",
                "score": None,
                "asof": None,
                "stale": False,
            }],
            "entity_hits": [],
            "searched_domains": [],
        }
        result = runner.invoke(app, ["recall", "pgvector"])
    assert result.exit_code == 0


def test_tawn_brief_command():
    with patch("tawn.cli.brief") as mock_brief:
        mock_brief.return_value = {
            "domain": "work",
            "summary": "Active work domain.",
            "entity_count": 5,
            "chunk_count": 12,
            "last_compiled": "2026-07-20T14:00:00",
            "staleness_hours": 0.5,
            "stale_chunk_count": 0,
        }
        result = runner.invoke(app, ["brief", "work"])
    assert result.exit_code == 0


def test_tawn_compile_command():
    with patch("tawn.cli.run_compile") as mock_compile:
        mock_compile.return_value = MagicMock(
            ok=True, files_processed=3, chunks_added=10,
            chunks_removed=0, entities_resolved=5, error=None,
        )
        result = runner.invoke(app, ["compile"])
    assert result.exit_code == 0


def test_tawn_compile_status_command():
    with patch("tawn.cli.compile_status") as mock_status:
        mock_status.return_value = {
            "last_compiled": "2026-07-20T14:00:00",
            "pending": False,
        }
        result = runner.invoke(app, ["compile", "--status"])
    assert result.exit_code == 0
    assert "2026-07-20" in result.output or "never" in result.output
