import pytest

from tawn.compiler.quality import is_garbage, is_low_value, prose_ratio


@pytest.mark.parametrize("text", [
    "[SYSTEM NOTIFICATION] agent finished",
    'Traceback (most recent call last):\n  File "a.py", line 1\n  File "b.py", line 2',
    "╭─ Error ─╮\n│ boom   │\n╰─────────╯",
])
def test_is_garbage_true(text):
    assert is_garbage(text) is True


def test_is_garbage_false_on_prose():
    assert is_garbage("We decided to use pgvector for semantic search.") is False


@pytest.mark.parametrize("text", [
    '{"name": "x", "lockfileVersion": 3, "requires": true}',      # lockfile
    "a" * 400,                                                     # minified blob
    "$ npm ci\nadded 1403 packages in 12s\nnpm WARN deprecated",   # tool output
])
def test_is_low_value_true(text):
    assert is_low_value(text) is True


def test_is_low_value_false_on_prose():
    assert is_low_value(
        "The compiler runs nine phases over the raw directory."
    ) is False


def test_is_low_value_keeps_short_prose():
    """A brief note is not low-value just for being brief."""
    assert is_low_value("Shipped v0.1.0 to PyPI.") is False


def test_prose_ratio_counts_words_over_symbols():
    assert prose_ratio("The quick brown fox jumps over the lazy dog") > 0.8
    assert prose_ratio("{[(=>;)]}{[(=>;)]}") < 0.2


def test_prose_ratio_empty_is_zero():
    assert prose_ratio("") == 0.0
