"""Attachments: parsed once on attach, referenced by id thereafter."""

import datetime
import zipfile

import pytest

from tawn.memory import attachments as att
from tawn.parsing import ParseError


def _docx(path, paragraphs):
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "word/document.xml",
            f'<?xml version="1.0"?><w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>',
        )
    return path.read_bytes()


# ── ingest ───────────────────────────────────────────────────────────────────

def test_a_text_file_is_parsed_on_attach(tmp_path):
    a = att.ingest(tmp_path, "notes.txt", b"hello world")
    assert a.format == "text"
    assert a.text == "hello world"
    assert a.chars == 11
    assert a.id


def test_a_docx_is_parsed_properly_not_read_as_text(tmp_path):
    """Reading a Word file as text yields binary noise. This is the bug that
    made attaching a document useless."""
    data = _docx(tmp_path / "src.docx", ["First para", "Second para"])
    a = att.ingest(tmp_path, "report.docx", data)
    assert a.format == "docx"
    assert "First para" in a.text
    assert "Second para" in a.text
    assert "PK" not in a.text  # no raw zip bytes leaked through


def test_the_format_is_detected_from_bytes_not_the_name(tmp_path):
    data = _docx(tmp_path / "src.docx", ["Real content"])
    a = att.ingest(tmp_path, "mislabelled.txt", data)
    assert a.format == "docx"
    assert "Real content" in a.text


def test_an_empty_file_is_refused(tmp_path):
    with pytest.raises(ParseError, match="empty"):
        att.ingest(tmp_path, "nothing.txt", b"")


def test_an_oversized_upload_is_refused_before_parsing(tmp_path, monkeypatch):
    monkeypatch.setattr(att, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(ParseError, match="attachment limit"):
        att.ingest(tmp_path, "big.txt", b"x" * 100)


def test_a_hostile_archive_is_refused(tmp_path):
    """Attachments go through the same harness as compile."""
    bomb = tmp_path / "bomb.docx"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", "0" * (5 * 1024 * 1024))
    with pytest.raises(ParseError):
        att.ingest(tmp_path, "bomb.docx", bomb.read_bytes())


def test_long_text_is_capped_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(att, "MAX_TEXT_CHARS", 100)
    a = att.ingest(tmp_path, "long.txt", b"y" * 5000)
    assert a.truncated is True
    assert "truncated" in a.text
    assert a.chars < 200


# ── storage ──────────────────────────────────────────────────────────────────

def test_round_trip(tmp_path):
    a = att.ingest(tmp_path, "notes.txt", b"remember this")
    got = att.load(tmp_path, a.id)
    assert got.text == "remember this"
    assert got.name == "notes.txt"


def test_meta_carries_no_text(tmp_path):
    """The UI gets size and format, not the payload."""
    a = att.ingest(tmp_path, "notes.txt", b"secret contents")
    assert "text" not in a.meta()
    assert a.meta()["chars"] == 15


def test_removal(tmp_path):
    a = att.ingest(tmp_path, "notes.txt", b"x")
    assert att.remove(tmp_path, a.id) is True
    assert att.load(tmp_path, a.id) is None
    assert att.remove(tmp_path, a.id) is False


def test_an_unknown_id_loads_as_none(tmp_path):
    assert att.load(tmp_path, "deadbeef") is None


def test_a_traversal_id_cannot_escape_the_store(tmp_path):
    secret = tmp_path / "secret.json"
    secret.write_text('{"id": "x", "name": "n", "format": "text", "chars": 1}')
    assert att.load(tmp_path, "../secret") is None


# ── the context block ────────────────────────────────────────────────────────

def test_the_block_names_each_document(tmp_path):
    a = att.ingest(tmp_path, "notes.txt", b"alpha")
    b = att.ingest(tmp_path, "other.txt", b"beta")
    block = att.context_block(tmp_path, [a.id, b.id])
    assert "attached: notes.txt" in block
    assert "alpha" in block and "beta" in block


def test_a_missing_id_is_skipped_not_fatal(tmp_path):
    a = att.ingest(tmp_path, "notes.txt", b"alpha")
    block = att.context_block(tmp_path, [a.id, "nonexistent"])
    assert "alpha" in block


def test_no_ids_yields_nothing(tmp_path):
    assert att.context_block(tmp_path, []) == ""


# ── sweeping ─────────────────────────────────────────────────────────────────

def test_old_attachments_are_swept(tmp_path):
    a = att.ingest(tmp_path, "old.txt", b"x")
    later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=72)
    assert att.sweep(tmp_path, now=later) == 1
    assert att.load(tmp_path, a.id) is None


def test_recent_attachments_survive(tmp_path):
    a = att.ingest(tmp_path, "new.txt", b"x")
    assert att.sweep(tmp_path) == 0
    assert att.load(tmp_path, a.id) is not None


def test_sweeping_an_empty_store(tmp_path):
    assert att.sweep(tmp_path) == 0
