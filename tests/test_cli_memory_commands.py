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


# ── Stage 7: tawn enrich ──────────────────────────────────────────────────────

def test_enrich_command_reports_result():
    from tawn.compiler.enrich import EnrichResult

    with patch("tawn.compiler.enrich.run_enrich") as mock_run:
        mock_run.return_value = EnrichResult(
            ok=True, chunks_enriched=7, groups_enriched=2, failed=0
        )
        result = runner.invoke(app, ["enrich"])

    assert result.exit_code == 0
    assert "7" in result.stdout
    assert "2" in result.stdout


def test_enrich_reports_missing_model_without_crashing():
    """No local model is a normal state, not a failure — exit 0 with a reason."""
    from tawn.compiler.enrich import EnrichResult

    with patch("tawn.compiler.enrich.run_enrich") as mock_run:
        mock_run.return_value = EnrichResult(
            ok=False, error="no model available: ollama down"
        )
        result = runner.invoke(app, ["enrich"])

    assert result.exit_code == 0
    assert "no model available" in result.stdout


def test_enrich_passes_limit_through():
    from tawn.compiler.enrich import EnrichResult

    with patch("tawn.compiler.enrich.run_enrich") as mock_run:
        mock_run.return_value = EnrichResult(ok=True)
        runner.invoke(app, ["enrich", "--limit", "42"])

    assert mock_run.call_args.kwargs["limit"] == 42


# ── Stage 7: tawn wiki ────────────────────────────────────────────────────────

def test_wiki_list_shows_domains(_home):
    (_home / "wiki" / "work").mkdir(parents=True, exist_ok=True)
    (_home / "wiki" / "work" / "index.md").write_text("# Work")
    result = runner.invoke(app, ["wiki", "list"])
    assert result.exit_code == 0
    assert "work" in result.stdout


def test_wiki_domain_renders_page(_home):
    (_home / "wiki" / "work").mkdir(parents=True, exist_ok=True)
    (_home / "wiki" / "work" / "index.md").write_text("# Work\n\nA line of prose.")
    result = runner.invoke(app, ["wiki", "work"])
    assert result.exit_code == 0
    assert "Work" in result.stdout


def test_wiki_missing_domain_hints_compile(_home):
    result = runner.invoke(app, ["wiki", "nope"])
    assert "compile" in result.stdout.lower()


def test_wiki_entity_fuzzy_match(_home):
    ents = _home / "wiki" / "entities"
    ents.mkdir(parents=True, exist_ok=True)
    (ents / "ClauseWise.md").write_text("# ClauseWise\n\nContract review.")
    result = runner.invoke(app, ["wiki", "entity", "clausewise"])
    assert result.exit_code == 0
    assert "ClauseWise" in result.stdout


def test_wiki_entity_no_match_reports(_home):
    ents = _home / "wiki" / "entities"
    ents.mkdir(parents=True, exist_ok=True)
    (ents / "ClauseWise.md").write_text("# ClauseWise")
    result = runner.invoke(app, ["wiki", "entity", "zzzzzzz"])
    assert "no entity" in result.stdout.lower()
