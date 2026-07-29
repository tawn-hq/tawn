"""Readable one-line previews for unenriched chunks."""

from tawn.memory.preview import preview_text


def test_strips_markdown_table_rows():
    src = "## Status Legend\n\n| Symbol | Meaning |\n|--------|---------|\n| OK | Implemented |"
    out = preview_text(src)
    assert "|" not in out
    assert "Status Legend" in out


def test_strips_heading_marks():
    assert preview_text("# Certin Engine — Architecture Audit").startswith("Certin Engine")


def test_truncates_on_word_boundary():
    src = "The quick brown fox jumps over the lazy dog and keeps running onward forever"
    out = preview_text(src, limit=30)
    assert len(out) <= 31  # + ellipsis
    assert not out.rstrip("…").endswith(("t", "n") ) or " " in out
    # The decisive property: no word is cut in half.
    assert out.rstrip("… ").split()[-1] in src.split()


def test_prefers_sentence_boundary_when_close():
    src = "Wired the eval harness. Then a lot of further detail follows here at length."
    out = preview_text(src, limit=40)
    assert out.startswith("Wired the eval harness.")


def test_collapses_whitespace_and_blank_lines():
    assert preview_text("a\n\n\n\nb   \n  c") == "a b c"


def test_drops_code_markers():
    assert "[code:" not in preview_text("Before [code: python, 24 lines] after")


def test_empty_input():
    assert preview_text("") == ""
    assert preview_text(None) == ""


def test_returns_prose_when_table_is_all_there_is():
    """A chunk that is only a table still needs to say something."""
    out = preview_text("| a | b |\n|---|---|\n| 1 | 2 |")
    assert out  # not empty
    assert "|" not in out
