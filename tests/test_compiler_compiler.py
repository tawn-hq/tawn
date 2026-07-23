"""Tests for the compiler orchestrator."""

import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.compiler.compiler import compile
from tawn.compiler.embedder import EmbedError
from tawn.memory.schema import Base, Chunk, CompileLog


@pytest.fixture()
def db(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def home(tmp_path, monkeypatch):
    h = tmp_path / "tawn_home"
    (h / "raw" / "agent-notes").mkdir(parents=True)
    (h / "wiki").mkdir()
    # keep the real ~/.claude/projects out of this isolated compile run
    monkeypatch.setenv("TAWN_AGENT_MEMORY_DIR", str(tmp_path / "claude-projects"))
    return h


def _write_md(home, subpath, content):
    p = home / "raw" / subpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


@patch("tawn.compiler.compiler.embed_text", side_effect=EmbedError("no embed"))
def test_compile_new_file(mock_embed, db, home):
    _write_md(home, "agent-notes/2026-07-20.md", "# Note\nSome text here.")
    log = compile(home, db)
    db.commit()
    assert log.ok is True
    assert log.files_processed == 1
    assert log.chunks_added >= 1


@patch("tawn.compiler.compiler.embed_text", side_effect=EmbedError("no embed"))
def test_compile_empty_raw_dir(mock_embed, db, home):
    log = compile(home, db)
    db.commit()
    assert log.ok is True
    assert log.files_processed == 0
    assert log.chunks_added == 0


@patch("tawn.compiler.compiler.embed_text", side_effect=EmbedError("no embed"))
def test_compile_logs_to_db(mock_embed, db, home):
    _write_md(home, "agent-notes/note.md", "Content.")
    compile(home, db)
    db.commit()
    logs = db.query(CompileLog).all()
    assert len(logs) == 1
    assert logs[0].ok is True
    assert logs[0].finished_at is not None


@patch("tawn.compiler.compiler.embed_text", side_effect=EmbedError("no embed"))
def test_compile_incremental_skips_unchanged(mock_embed, db, home):
    _write_md(home, "agent-notes/note.md", "Stable content.")
    compile(home, db)
    db.commit()
    log2 = compile(home, db)
    db.commit()
    assert log2.files_processed == 0


@patch("tawn.compiler.compiler.embed_text", side_effect=EmbedError("no embed"))
def test_compile_generates_wiki(mock_embed, db, home):
    (home / "wiki" / ".staging").mkdir(parents=True, exist_ok=True)
    _write_md(home, "agent-notes/note.md", "---\ndomain: work\n---\n# Hello\nThis is text.")
    result = compile(home, db)
    db.commit()
    assert result.ok is True
    assert (home / "wiki" / "work" / "index.md").exists()
