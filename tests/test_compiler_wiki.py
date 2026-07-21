import datetime
import pytest

from tawn.compiler.parser import ParsedChunk
from tawn.compiler.wiki import generate_wiki
from tawn.memory.schema import Entity


def _chunk(content, source="raw/agent-notes/note.md", domain="work"):
    return ParsedChunk(
        source_path=source,
        chunk_index=0,
        content=content,
        frontmatter={"domain": domain},
        priority_tier=3,
        asof=datetime.datetime.utcnow(),
    )


def _entity(canonical, domain=None):
    e = Entity(canonical=canonical, domain=domain, source_path="raw/identity/me.md")
    return e


def test_generates_domain_page(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    chunks = [_chunk("Tawn is a personal twin.", domain="work")]
    generate_wiki(chunks, [], wiki)
    page = wiki / "domains" / "work.md"
    assert page.exists()
    assert "# Domain: work" in page.read_text()


def test_generates_entity_page(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    entity = _entity("Tawn", domain="work")
    chunks = [_chunk("Tawn is a personal twin.")]
    generate_wiki(chunks, [entity], wiki)
    page = wiki / "entities" / "Tawn.md"
    assert page.exists()
    text = page.read_text()
    assert "# Entity: Tawn" in text


def test_generates_index(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    chunks = [_chunk("content", domain="research")]
    entity = _entity("pgvector")
    generate_wiki(chunks, [entity], wiki)
    index = wiki / "index.md"
    assert index.exists()
    text = index.read_text()
    assert "research" in text
    assert "pgvector" in text


def test_conflicts_md_preserved(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "conflicts.md").write_text("## Old conflict\n")
    generate_wiki([], [], wiki)
    assert (wiki / "conflicts.md").read_text() == "## Old conflict\n"


def test_staging_dir_cleaned_up(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    generate_wiki([], [], wiki)
    assert not (wiki / ".staging").exists()


def test_entity_page_lists_references(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    entity = _entity("PostgreSQL")
    chunks = [
        _chunk("PostgreSQL is a great DB.", domain="work"),
        _chunk("No mention here.", domain="hobby"),
    ]
    generate_wiki(chunks, [entity], wiki)
    page = (wiki / "entities" / "PostgreSQL.md").read_text()
    assert "raw/agent-notes/note.md" in page
