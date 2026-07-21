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
