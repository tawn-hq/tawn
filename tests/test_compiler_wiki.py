"""Tests for wiki generation.

Rewritten for Stage 7: the previous suite targeted `generate_wiki()`, a
full-corpus generator writing a `wiki/domains/*.md` layout that the compiler
never called and that never existed on disk. Only the
`generate_domain_index` + `atomic_swap` path is real.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.compiler.wiki import (
    atomic_swap,
    generate_domain_index,
    generate_entity_page,
    generate_links_index,
    wikilink,
)
from tawn.memory.schema import Base, Entity, EntityEdge


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_wikilink_wraps_name():
    assert wikilink("pgvector") == "[[pgvector]]"


def test_entity_page_has_frontmatter_and_links(tmp_path):
    staging = tmp_path / ".staging"
    staging.mkdir()
    ent = Entity(canonical="ClauseWise", domain="work", confidence="high")

    path = generate_entity_page(
        ent,
        related=[("pgvector", "uses"), ("RiskPanel", "mentioned with")],
        backlinks=["Tawn"],
        staging_dir=staging,
    )

    text = path.read_text()
    assert path.name == "ClauseWise.md"
    assert "domain: work" in text
    assert "[[pgvector]]" in text
    assert "[[RiskPanel]]" in text
    assert "## Linked from" in text
    assert "[[Tawn]]" in text


def test_entity_page_sanitises_filename(tmp_path):
    staging = tmp_path / ".staging"
    staging.mkdir()
    path = generate_entity_page(
        Entity(canonical="a/b:c"), related=[], backlinks=[], staging_dir=staging
    )
    assert "/" not in path.name
    assert ":" not in path.name


def test_entity_page_without_links_still_written(tmp_path):
    staging = tmp_path / ".staging"
    staging.mkdir()
    path = generate_entity_page(
        Entity(canonical="Lonely"), related=[], backlinks=[], staging_dir=staging
    )
    assert path.exists()
    assert "# Lonely" in path.read_text()


def test_links_index_emits_nodes_and_edges(tmp_path, db):
    staging = tmp_path / ".staging"
    staging.mkdir()
    a = Entity(canonical="A", domain="work")
    b = Entity(canonical="B", domain="research")
    db.add_all([a, b])
    db.flush()
    db.add(EntityEdge(from_entity_id=a.id, to_entity_id=b.id, relation="uses", weight=3))
    db.commit()

    path = generate_links_index(db, staging)

    data = json.loads(path.read_text())
    assert path.name == "links.json"
    assert {n["label"] for n in data["nodes"]} == {"A", "B"}
    assert data["links"][0]["relation"] == "uses"
    assert data["links"][0]["weight"] == 3


def test_links_index_empty_corpus(tmp_path, db):
    staging = tmp_path / ".staging"
    staging.mkdir()
    data = json.loads(generate_links_index(db, staging).read_text())
    assert data == {"nodes": [], "links": []}


def test_domain_index_still_written(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    staging = wiki / ".staging"
    staging.mkdir()

    generate_domain_index("work", ["Tawn"], ["a note"], wiki, staging, router=None)

    assert (staging / "work" / "index.md").exists()


def test_atomic_swap_moves_domain_dirs(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    staging = wiki / ".staging"
    (staging / "work").mkdir(parents=True)
    (staging / "work" / "index.md").write_text("# Work")

    atomic_swap(staging, wiki)

    assert (wiki / "work" / "index.md").read_text() == "# Work"


def test_atomic_swap_carries_top_level_files(tmp_path):
    """links.json sits at the wiki root, not inside a domain dir."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    staging = wiki / ".staging"
    staging.mkdir(parents=True)
    (staging / "links.json").write_text('{"nodes": [], "links": []}')

    atomic_swap(staging, wiki)

    assert (wiki / "links.json").exists()


def test_atomic_swap_prunes_stale_domains(tmp_path):
    """A domain that stops producing chunks must lose its page.

    This is the research/index.md symptom: a page for a domain with zero
    chunks survived every compile, because the swap only replaced what it
    found in staging.
    """
    wiki = tmp_path / "wiki"
    (wiki / "research").mkdir(parents=True)
    (wiki / "research" / "index.md").write_text("# Research (stale)")
    staging = wiki / ".staging"
    (staging / "work").mkdir(parents=True)
    (staging / "work" / "index.md").write_text("# Work")

    atomic_swap(staging, wiki)

    assert (wiki / "work" / "index.md").exists()
    assert not (wiki / "research").exists()


def test_atomic_swap_keeps_entities_dir(tmp_path):
    """Entity pages are not domains and must survive a domain-only swap."""
    wiki = tmp_path / "wiki"
    (wiki / "entities").mkdir(parents=True)
    (wiki / "entities" / "Tawn.md").write_text("# Tawn")
    staging = wiki / ".staging"
    (staging / "work").mkdir(parents=True)
    (staging / "work" / "index.md").write_text("# Work")

    atomic_swap(staging, wiki)

    assert (wiki / "entities" / "Tawn.md").exists()


def test_atomic_swap_does_not_prune_when_nothing_was_staged(tmp_path):
    """An empty staging dir means the run generated nothing — not that every
    domain disappeared. Pruning on that basis deleted all live domain pages
    after a compile where no file had changed."""
    wiki = tmp_path / "wiki"
    (wiki / "work").mkdir(parents=True)
    (wiki / "work" / "index.md").write_text("# Work")
    staging = wiki / ".staging"
    staging.mkdir(parents=True)

    atomic_swap(staging, wiki)

    assert (wiki / "work" / "index.md").exists()


def test_atomic_swap_prune_can_be_disabled(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "research").mkdir(parents=True)
    (wiki / "research" / "index.md").write_text("# Research")
    staging = wiki / ".staging"
    (staging / "work").mkdir(parents=True)
    (staging / "work" / "index.md").write_text("# Work")

    atomic_swap(staging, wiki, prune=False)

    assert (wiki / "research" / "index.md").exists()
    assert (wiki / "work" / "index.md").exists()
