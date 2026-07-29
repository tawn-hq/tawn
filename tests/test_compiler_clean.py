from tawn.compiler.clean import clean_chunk, collapse_code_blocks


def test_collapses_fenced_code_block_with_language():
    src = "Before\n\n```python\nx = 1\ny = 2\n```\n\nAfter"
    out = collapse_code_blocks(src)
    assert "[code: python, 2 lines]" in out
    assert "x = 1" not in out
    assert "Before" in out and "After" in out


def test_collapses_fenced_block_without_language():
    src = "```\nsome output\n```"
    assert "[code: 1 lines]" in collapse_code_blocks(src)


def test_collapses_multiple_blocks():
    src = "```py\na = 1\n```\ntext\n```sh\nls\n```"
    out = collapse_code_blocks(src)
    assert out.count("[code:") == 2
    assert "text" in out


def test_leaves_inline_code_alone():
    src = "Call `compute_all_metrics()` first."
    assert collapse_code_blocks(src) == src


def test_clean_chunk_normalises_whitespace():
    assert clean_chunk("a\n\n\n\n\nb   \n") == "a\n\nb"


def test_clean_chunk_strips_tool_envelopes():
    src = "<system-reminder>ignore me</system-reminder>\nReal content here."
    out = clean_chunk(src)
    assert "system-reminder" not in out
    assert "Real content here." in out


def test_clean_chunk_returns_empty_for_all_code():
    assert clean_chunk("```python\nx = 1\n```") == ""


def test_clean_chunk_keeps_prose_around_code():
    src = "We chose pgvector because it fits.\n\n```sql\nCREATE EXTENSION vector;\n```"
    out = clean_chunk(src)
    assert "We chose pgvector because it fits." in out
    assert "[code: sql, 1 lines]" in out


def test_clean_chunk_empty_input():
    assert clean_chunk("") == ""
