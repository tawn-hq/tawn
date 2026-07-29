"""Detect a running process older than the code on disk."""

import time
from pathlib import Path

import pytest

from tawn.staleness import (
    code_fingerprint,
    read_running_fingerprint,
    staleness_report,
    write_running_fingerprint,
)


def test_fingerprint_is_stable_across_calls():
    assert code_fingerprint() == code_fingerprint()


def test_fingerprint_changes_when_a_source_file_is_touched(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1")
    first = code_fingerprint(pkg)

    time.sleep(0.01)
    (pkg / "a.py").write_text("x = 2")
    assert code_fingerprint(pkg) != first


def test_fingerprint_ignores_non_python_and_caches(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "__pycache__").mkdir(parents=True)
    (pkg / "a.py").write_text("x = 1")
    baseline = code_fingerprint(pkg)

    (pkg / "notes.txt").write_text("irrelevant")
    (pkg / "__pycache__" / "a.cpython-312.pyc").write_text("bytecode")
    assert code_fingerprint(pkg) == baseline


def test_write_then_read_roundtrip(tmp_path):
    write_running_fingerprint(tmp_path, "web", "abc123")
    assert read_running_fingerprint(tmp_path, "web") == "abc123"


def test_read_missing_fingerprint_is_none(tmp_path):
    assert read_running_fingerprint(tmp_path, "web") is None


def test_report_flags_stale_process(tmp_path):
    write_running_fingerprint(tmp_path, "web", "old-fingerprint")
    report = staleness_report(tmp_path, "web", current="new-fingerprint")

    assert report["stale"] is True
    assert report["running"] == "old-fingerprint"
    assert report["current"] == "new-fingerprint"
    assert "restart" in report["advice"].lower()


def test_report_clean_when_matching(tmp_path):
    write_running_fingerprint(tmp_path, "web", "same")
    report = staleness_report(tmp_path, "web", current="same")

    assert report["stale"] is False
    assert report["advice"] == ""


def test_report_unknown_when_no_fingerprint_recorded(tmp_path):
    """A process started before this check existed cannot be judged stale."""
    report = staleness_report(tmp_path, "web", current="whatever")
    assert report["stale"] is False
    assert report["running"] is None
