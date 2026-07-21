"""Tests for compiler orchestrator (Task 10)."""

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tawn.compiler.compiler import (
    CompileResult,
    compile_status,
    request_compile,
    run_compile,
    should_compile,
)
from tawn.memory.schema import Base, Chunk, CompileLog


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "tawn"
    for sub in ["raw/agent-notes", "raw/identity", "raw/vault",
                "raw/review-queue", "wiki", "wiki/.staging"]:
        (h / sub).mkdir(parents=True)
    return h


@pytest.fixture()
def db(home):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@patch("tawn.compiler.compiler.embed_text", return_value=[0.1] * 1024)
def test_compile_empty_raw_succeeds(mock_embed, home, db):
    result = run_compile(home, db)
    assert result.ok is True
    assert result.files_processed == 0


@patch("tawn.compiler.compiler.embed_text", return_value=[0.1] * 1024)
def test_compile_processes_new_note(mock_embed, home, db):
    note = home / "raw" / "agent-notes" / "2026-07-20.md"
    note.write_text("---\ntype: decision\ndomain: work\n---\nUsing pgvector.\n")
    result = run_compile(home, db)
    assert result.ok is True
    assert result.files_processed >= 1
    assert result.chunks_added >= 1
    assert db.query(Chunk).count() >= 1


@patch("tawn.compiler.compiler.embed_text", return_value=[0.1] * 1024)
def test_compile_logs_to_compile_log(mock_embed, home, db):
    run_compile(home, db)
    assert db.query(CompileLog).count() == 1
    log = db.query(CompileLog).first()
    assert log.ok is True
    assert log.finished_at is not None


@patch("tawn.compiler.compiler.embed_text", return_value=[0.1] * 1024)
def test_compile_status_returns_dict(mock_embed, home, db):
    run_compile(home, db)
    status = compile_status(home, db)
    assert "last_compiled" in status
    assert "pending" in status


def test_request_compile_creates_sentinel(home):
    request_compile(home)
    assert (home / ".compile-requested").exists()


def test_should_compile_false_when_no_sentinel(home):
    assert should_compile(home) is False


def test_should_compile_true_after_quiet_period(home):
    sentinel = home / ".compile-requested"
    sentinel.touch()
    old_time = time.time() - 60
    os.utime(sentinel, (old_time, old_time))
    assert should_compile(home, quiet_seconds=30) is True


def test_should_compile_false_within_quiet_period(home):
    (home / ".compile-requested").touch()
    assert should_compile(home, quiet_seconds=30) is False


@patch("tawn.compiler.compiler.embed_text", return_value=[0.1] * 1024)
def test_rebuild_clears_chunks(mock_embed, home, db):
    note = home / "raw" / "agent-notes" / "note.md"
    note.write_text("First compile.\n")
    run_compile(home, db)
    assert db.query(Chunk).count() >= 1
    run_compile(home, db, rebuild=True)
    assert db.query(Chunk).count() >= 1


def test_compile_result_dataclass():
    r = CompileResult(ok=True, files_processed=2, chunks_added=5)
    assert r.ok is True
    assert r.error is None
