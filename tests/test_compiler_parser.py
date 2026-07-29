import datetime
import textwrap
from pathlib import Path
import pytest
from tawn.compiler.parser import parse_file, tier_for_path, ParsedChunk


@pytest.fixture()
def raw_dir(tmp_path):
    d = tmp_path / "raw"
    for sub in ["identity", "vault", "agent-notes", "review-queue"]:
        (d / sub).mkdir(parents=True)
    return d


def test_tier_identity(raw_dir):
    assert tier_for_path(raw_dir / "identity" / "me.md") == 1


def test_tier_vault(raw_dir):
    assert tier_for_path(raw_dir / "vault" / "notes.md") == 2


def test_tier_agent_notes(raw_dir):
    assert tier_for_path(raw_dir / "agent-notes" / "2026-07-20.md") == 3


def test_tier_federation(raw_dir):
    assert tier_for_path(raw_dir.parent / "federation" / "inbox" / "gpt.md") == 4


def test_tier_unknown_defaults_to_3(tmp_path):
    assert tier_for_path(tmp_path / "some" / "other" / "file.md") == 3


def test_parse_simple_note(raw_dir):
    note = raw_dir / "agent-notes" / "2026-07-20.md"
    note.write_text(textwrap.dedent("""\
        ---
        type: decision
        domain: work
        confidence: high
        asof: 2026-07-20T14:32:00Z
        ttl_days: 90
        ---
        Decided to use pgvector over Chroma. Existing Postgres, one less service.
    """))
    chunks = parse_file(note)
    assert len(chunks) >= 1
    c = chunks[0]
    assert c.chunk_index == 0
    assert "pgvector" in c.content
    assert c.frontmatter["type"] == "decision"
    assert c.priority_tier == 3
    assert c.ttl_days == 90


def test_parse_large_file_splits_chunks(raw_dir):
    sections = []
    for i in range(10):
        sections.append(f"## Section {i}\n\n" + ("word " * 200))
    note = raw_dir / "vault" / "big.md"
    note.write_text("\n\n".join(sections))
    chunks = parse_file(note)
    assert len(chunks) >= 2
    for i, c in enumerate(chunks):
        assert c.chunk_index == i


def test_parse_no_frontmatter(raw_dir):
    note = raw_dir / "identity" / "profile.md"
    note.write_text("I am a researcher at X university.\n")
    chunks = parse_file(note)
    assert len(chunks) == 1
    assert chunks[0].priority_tier == 1


def test_parse_sets_asof_from_frontmatter(raw_dir):
    note = raw_dir / "agent-notes" / "dated.md"
    note.write_text("---\nasof: 2026-01-15T10:00:00Z\n---\nSome content.\n")
    chunks = parse_file(note)
    assert chunks[0].asof.year == 2026
    assert chunks[0].asof.month == 1


def test_parse_content_hash_set(raw_dir):
    note = raw_dir / "identity" / "me.md"
    note.write_text("I am Testimony.\n")
    chunks = parse_file(note)
    assert len(chunks[0].content_hash) == 16


# ── Stage 7: cleaning + grouping ──────────────────────────────────────────────

def test_parse_file_cleans_code_blocks(tmp_path):
    p = tmp_path / "note.md"
    p.write_text("Decision made about routing.\n\n```python\nx = 1\ny = 2\n```\n\nRationale follows here.")
    chunks = parse_file(p, home=tmp_path)
    assert chunks
    body = chunks[0].content
    assert "[code: python, 2 lines]" in body
    assert "x = 1" not in body


def test_parse_file_sets_group_fields(tmp_path):
    p = tmp_path / "note.md"
    p.write_text("Some durable content about the project and its direction.")
    chunks = parse_file(p, home=tmp_path)
    assert chunks[0].group_key == str(p)
    assert chunks[0].group_label == "note.md"


def test_parse_file_drops_low_value_chunks(tmp_path):
    p = tmp_path / "log.md"
    p.write_text("added 1403 packages in 12s\nnpm WARN deprecated foo@1.0.0")
    assert parse_file(p, home=tmp_path) == []


def test_parse_text_file_sets_group_fields(tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("A plain text note that carries some real meaning.")
    chunks = parse_file(p, home=tmp_path)
    assert chunks[0].group_key == str(p)


def test_agent_memory_file_is_ungrouped(tmp_path):
    mem = tmp_path / ".claude" / "projects" / "p" / "memory"
    mem.mkdir(parents=True)
    p = mem / "fact.md"
    p.write_text("The user prefers inline execution over subagents.")
    chunks = parse_file(p, home=tmp_path)
    assert chunks[0].group_key is None


# ── Stage 7 follow-up: classified domain must reach the chunk ─────────────────

def test_parse_file_applies_inferred_domain_to_markdown(tmp_path):
    """The compiler classifies external files and passes the result in.

    For markdown it was silently discarded: parse_file built frontmatter from
    the file alone, so every classified external .md landed with domain NULL.
    """
    p = tmp_path / "note.md"
    p.write_text("A durable decision about the routing layer and its tradeoffs.")
    chunks = parse_file(p, domain="research", home=tmp_path)
    assert chunks
    assert chunks[0].frontmatter.get("domain") == "research"


def test_explicit_frontmatter_domain_beats_inference(tmp_path):
    """An author's own declaration outranks a guess."""
    p = tmp_path / "note.md"
    p.write_text("---\ndomain: wealth\n---\n\nPortfolio rebalancing notes for the quarter.")
    chunks = parse_file(p, domain="research", home=tmp_path)
    assert chunks[0].frontmatter.get("domain") == "wealth"


def test_no_domain_argument_leaves_frontmatter_untouched(tmp_path):
    p = tmp_path / "note.md"
    p.write_text("Content with no domain anywhere in sight, just prose.")
    chunks = parse_file(p, home=tmp_path)
    assert chunks[0].frontmatter.get("domain") is None


def test_text_file_inferred_domain_still_applies(tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("A plain text note that carries some real meaning about work.")
    chunks = parse_file(p, domain="work", home=tmp_path)
    assert chunks[0].frontmatter.get("domain") == "work"
