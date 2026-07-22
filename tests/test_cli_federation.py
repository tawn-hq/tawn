"""Tests for tawn federation CLI commands."""
import os
from unittest.mock import MagicMock, patch
import pytest
from typer.testing import CliRunner
from tawn.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _home(tmp_path):
    h = tmp_path / "tawn"
    (h / "raw" / "imports").mkdir(parents=True)
    (h / "federation" / "adapters").mkdir(parents=True)
    (h / "federation" / "exports").mkdir(parents=True)
    os.environ["TAWN_HOME"] = str(h)
    yield h
    del os.environ["TAWN_HOME"]


def test_federation_sources_empty():
    result = runner.invoke(app, ["federation", "sources"])
    assert result.exit_code == 0
    assert "no sources" in result.output.lower() or result.output.strip() == ""


def test_federation_add_source():
    result = runner.invoke(app, ["federation", "add", "hermes", "~/.hermes/"])
    assert result.exit_code == 0
    assert "hermes" in result.output


def test_federation_remove_source():
    runner.invoke(app, ["federation", "add", "hermes", "~/.hermes/"])
    result = runner.invoke(app, ["federation", "remove", "hermes"])
    assert result.exit_code == 0
    assert "removed" in result.output.lower() or "hermes" in result.output


def test_federation_merge():
    with patch("tawn.cli.merge_pending") as mock_merge:
        mock_merge.return_value = {"merged": 0, "failed": 0, "skipped": 0}
        result = runner.invoke(app, ["federation", "merge"])
    assert result.exit_code == 0


def test_tawn_export():
    with patch("tawn.cli.do_export") as mock_export:
        mock_export.return_value = {"ok": True, "format": "both",
                                    "out": "/tmp/export", "files": []}
        result = runner.invoke(app, ["export"])
    assert result.exit_code == 0
    assert "ok" in result.output.lower() or "export" in result.output.lower()


def test_tawn_help():
    result = runner.invoke(app, ["help"])
    assert result.exit_code == 0
    assert "tawn" in result.output.lower()
