import datetime
from pathlib import Path
import pytest
from tawn.compiler.parser import ParsedChunk
from tawn.compiler.conflicts import resolve_conflicts


def _chunk(content: str, tier: int, source: str = "raw/agent-notes/a.md") -> ParsedChunk:
    return ParsedChunk(
        source_path=source,
        chunk_index=0,
        content=content,
        priority_tier=tier,
        asof=datetime.datetime.utcnow(),
    )


def test_no_conflict_returns_all(tmp_path):
    chunks = [_chunk("Alpha content", 1), _chunk("Beta content", 3)]
    result = resolve_conflicts(chunks, wiki_dir=tmp_path)
    assert len(result) == 2


def test_same_content_higher_tier_wins(tmp_path):
    shared = "Same fact stated twice"
    high = _chunk(shared, 1, "raw/identity/me.md")
    low = _chunk(shared, 3, "raw/agent-notes/day.md")
    result = resolve_conflicts([high, low], wiki_dir=tmp_path)
    assert len(result) == 1
    assert result[0].priority_tier == 1


def test_lower_tier_number_wins_when_competing(tmp_path):
    shared = "Competing fact"
    a = _chunk(shared, 2, "raw/vault/v.md")
    b = _chunk(shared, 3, "raw/agent-notes/a.md")
    result = resolve_conflicts([a, b], wiki_dir=tmp_path)
    assert len(result) == 1
    assert result[0].priority_tier == 2


def test_unique_chunks_all_kept(tmp_path):
    chunks = [_chunk("Unique A", 3), _chunk("Unique B", 4)]
    result = resolve_conflicts(chunks, wiki_dir=tmp_path)
    assert len(result) == 2


def test_conflict_written_to_wiki(tmp_path):
    shared = "Conflicting fact"
    chunks = [
        _chunk(shared, 2, "raw/vault/v.md"),
        _chunk(shared, 3, "raw/agent-notes/a.md"),
    ]
    resolve_conflicts(chunks, wiki_dir=tmp_path)
    conflicts_file = tmp_path / "conflicts.md"
    assert conflicts_file.exists()
    text = conflicts_file.read_text()
    assert "vault" in text or "Conflicting" in text


def test_no_wiki_dir_no_crash(tmp_path):
    shared = "Shared content"
    chunks = [_chunk(shared, 1), _chunk(shared, 3)]
    result = resolve_conflicts(chunks, wiki_dir=None)
    assert len(result) == 1
