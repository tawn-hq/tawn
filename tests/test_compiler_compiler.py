"""Tests for the compiler orchestrator."""

import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.compiler.compiler import compile
from tawn.compiler.embedder import EmbedError
from tawn.memory.schema import Base, Chunk, CompileLog


@pytest.fixture()
def db(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def home(tmp_path, monkeypatch):
    h = tmp_path / "tawn_home"
    (h / "raw" / "agent-notes").mkdir(parents=True)
    (h / "wiki").mkdir()
    # keep the real ~/.claude/projects out of this isolated compile run
    monkeypatch.setenv("TAWN_AGENT_MEMORY_DIR", str(tmp_path / "claude-projects"))
    return h


def _write_md(home, subpath, content):
    p = home / "raw" / subpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


@patch("tawn.compiler.compiler.embed_texts", side_effect=EmbedError("no embed"))
def test_compile_new_file(mock_embed, db, home):
    _write_md(home, "agent-notes/2026-07-20.md", "# Note\nSome text here.")
    log = compile(home, db)
    db.commit()
    assert log.ok is True
    assert log.files_processed == 1
    assert log.chunks_added >= 1


@patch("tawn.compiler.compiler.embed_texts", side_effect=EmbedError("no embed"))
def test_compile_empty_raw_dir(mock_embed, db, home):
    log = compile(home, db)
    db.commit()
    assert log.ok is True
    assert log.files_processed == 0
    assert log.chunks_added == 0


@patch("tawn.compiler.compiler.embed_texts", side_effect=EmbedError("no embed"))
def test_compile_logs_to_db(mock_embed, db, home):
    _write_md(home, "agent-notes/note.md", "Content.")
    compile(home, db)
    db.commit()
    logs = db.query(CompileLog).all()
    assert len(logs) == 1
    assert logs[0].ok is True
    assert logs[0].finished_at is not None


@patch("tawn.compiler.compiler.embed_texts", side_effect=EmbedError("no embed"))
def test_compile_incremental_skips_unchanged(mock_embed, db, home):
    _write_md(home, "agent-notes/note.md", "Stable content.")
    compile(home, db)
    db.commit()
    log2 = compile(home, db)
    db.commit()
    assert log2.files_processed == 0


@patch("tawn.compiler.compiler.embed_texts", side_effect=EmbedError("no embed"))
def test_compile_generates_wiki(mock_embed, db, home):
    (home / "wiki" / ".staging").mkdir(parents=True, exist_ok=True)
    _write_md(home, "agent-notes/note.md", "---\ndomain: work\n---\n# Hello\nThis is text.")
    result = compile(home, db)
    db.commit()
    assert result.ok is True
    assert (home / "wiki" / "work" / "index.md").exists()


# ── Stage 7: group persistence + entity purge ─────────────────────────────────

def test_compile_persists_group_fields(home, db):
    from tawn.memory.schema import ChunkGroup

    _write_md(home, "agent-notes/a.md", "A durable decision about the routing layer.")
    compile(home, db)

    chunk = db.query(Chunk).first()
    assert chunk is not None
    assert chunk.group_key is not None
    grp = db.query(ChunkGroup).filter_by(group_key=chunk.group_key).one()
    assert grp.chunk_count >= 1


def test_rebuild_purges_entities(home, db):
    from tawn.memory.schema import Entity

    db.add(Entity(canonical="Stale Entity"))
    db.commit()

    compile(home, db, rebuild=True)

    assert db.query(Entity).filter_by(canonical="Stale Entity").count() == 0


def test_rebuild_purges_chunk_groups(home, db):
    from tawn.memory.schema import ChunkGroup

    db.add(ChunkGroup(group_key="/gone.md", chunk_count=9))
    db.commit()

    compile(home, db, rebuild=True)

    assert db.query(ChunkGroup).filter_by(group_key="/gone.md").count() == 0


def test_compile_purges_previously_indexed_review_queue(home, db):
    """Installs that indexed review-queue before it was excluded get cleaned."""
    import datetime as _dt

    db.add(Chunk(
        source_path=str(home / "raw" / "review-queue" / "entity-conflicts.md"),
        chunk_index=0, content="## Ambiguous: 'OK Traceback'",
        content_hash="h" * 16, asof=_dt.datetime.utcnow(),
        compiled_at=_dt.datetime.utcnow(),
    ))
    db.commit()
    assert db.query(Chunk).count() == 1

    compile(home, db)

    remaining = [c.source_path for c in db.query(Chunk).all()]
    assert not any("review-queue" in p for p in remaining)


def test_rebuild_does_not_reingest_review_queue(home, db):
    rq = home / "raw" / "review-queue"
    rq.mkdir(parents=True, exist_ok=True)
    (rq / "entity-conflicts.md").write_text("## Ambiguous: 'None File'\n")
    _write_md(home, "agent-notes/real.md", "A real durable note about routing.")

    compile(home, db, rebuild=True)

    paths = [c.source_path for c in db.query(Chunk).all()]
    assert any("real.md" in p for p in paths)
    assert not any("review-queue" in p for p in paths)


# ── Stage 7: embedding is not repeated for unchanged chunks ───────────────────

def test_unchanged_chunks_are_not_re_embedded(home, db, monkeypatch):
    """The whole corpus used to be re-embedded on every compile and discarded."""
    import tawn.compiler.compiler as comp

    calls = {"n": 0}

    def fake_embed_texts(texts, home_, batch_size=32):
        calls["n"] += len(texts)
        return [[0.1] * 8 for _ in texts], "fake-embed", 8

    monkeypatch.setattr(comp, "embed_texts", fake_embed_texts)

    _write_md(home, "agent-notes/a.md", "A durable decision about the routing layer.")
    compile(home, db)
    first = calls["n"]
    assert first > 0, "first compile must embed"

    # Nothing changed on disk — a second pass must not pay for embedding again.
    compile(home, db)
    assert calls["n"] == first


def test_changed_content_is_re_embedded(home, db, monkeypatch):
    import tawn.compiler.compiler as comp

    calls = {"n": 0}

    def fake_embed_texts(texts, home_, batch_size=32):
        calls["n"] += len(texts)
        return [[0.1] * 8 for _ in texts], "fake-embed", 8

    monkeypatch.setattr(comp, "embed_texts", fake_embed_texts)

    p = _write_md(home, "agent-notes/a.md", "First version of the note about routing.")
    compile(home, db)
    first = calls["n"]

    p.write_text("Second and quite different version of the note about storage.")
    compile(home, db)
    assert calls["n"] > first


def test_commits_interleave_with_embedding(home, db, monkeypatch):
    """Embedding must not be hoisted into a commit-free pre-pass.

    Regression guard: a speed refactor once computed every vector before
    writing anything, so a long rebuild held all progress in one uncommitted
    transaction — the exact failure the 2026-07-23 batched-commit decision
    fixed, and with every vector resident in memory meanwhile.
    """
    import tawn.compiler.compiler as comp

    order: list[str] = []

    def fake_embed_texts(texts, home_, batch_size=32):
        order.append(f"embed:{len(texts)}")
        return [[0.1] * 8 for _ in texts], "fake-embed", 8

    monkeypatch.setattr(comp, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(comp, "EMBED_GROUP", 4)
    monkeypatch.setattr(comp, "WRITE_BATCH", 4)

    real_commit = db.commit

    def tracking_commit():
        order.append("commit")
        return real_commit()

    monkeypatch.setattr(db, "commit", tracking_commit)

    # Enough chunks to span several embed windows and at least one commit batch.
    for n in range(12):
        _write_md(home, f"agent-notes/n{n}.md", f"Durable note number {n} about routing decisions.")

    compile(home, db)

    embeds = [i for i, o in enumerate(order) if o.startswith("embed:")]
    commits = [i for i, o in enumerate(order) if o == "commit"]
    assert embeds, "expected embedding to happen"
    assert commits, "expected at least one commit"
    # The defining property: a commit lands before the final embed call,
    # i.e. writing is interleaved rather than deferred to the end.
    assert any(c < embeds[-1] for c in commits), (
        f"all commits happened after the last embed — embedding was hoisted: {order}"
    )


def test_switching_embedder_forces_re_embed_at_same_width(home, db, monkeypatch):
    """Same dims, different model must NOT be treated as a valid vector.

    nomic-embed-text and gemini-embedding-001 are both 768-dimensional but
    share no geometry, so reusing one for the other silently corrupts recall.
    """
    import datetime
    import tawn.compiler.compiler as comp
    from tawn.memory.schema import Chunk

    (home / "config.yaml").write_text(
        "embed_model: gemini-embedding-001\nembed_dims: 768\n"
    )
    p = _write_md(home, "agent-notes/a.md", "A durable decision about the routing layer.")

    embedded: list[int] = []

    def fake_embed_texts(texts, home_, batch_size=32):
        embedded.append(len(texts))
        return [[0.5] * 768 for _ in texts], "gemini-embedding-001", 768

    monkeypatch.setattr(comp, "embed_texts", fake_embed_texts)
    compile(home, db)
    assert embedded, "first compile should embed"

    # Rewrite every stored vector as if produced by the *other* 768-dim model.
    for c in db.query(Chunk).all():
        c.embed_model = "nomic-embed-text"
        c.embed_dims = 768
    db.commit()
    embedded.clear()

    compile(home, db)
    # A normal compile only reconsiders chunks whose *files* changed, so it
    # does NOT repair stale-model vectors on its own — that is what
    # `reembed_stale` exists for. Asserted here so the boundary is explicit.
    assert not embedded, "unchanged files should not be re-parsed by compile"

    from tawn.compiler.embedder import embed_texts as _et
    import tawn.compiler.reembed as re_mod
    monkeypatch.setattr(re_mod, "embed_texts", fake_embed_texts)
    n = re_mod.reembed_stale(db, home)
    assert n == db.query(Chunk).count(), "every stale-model chunk must be re-embedded"
    assert all(c.embed_model == "gemini-embedding-001" for c in db.query(Chunk).all())
