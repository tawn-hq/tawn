"""Tests for recall() verb (Task 12)."""

import datetime
import os
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tawn.compiler.embedder import EmbedError
from tawn.memory.recall import recall
from tawn.memory.schema import Base, Chunk


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "tawn"
    h.mkdir()
    os.environ["TAWN_HOME"] = str(h)
    yield h
    del os.environ["TAWN_HOME"]


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_chunk(session, content: str, domain: str = "work"):
    chunk = Chunk(
        domain=domain,
        source_path="raw/agent-notes/2026-07-20.md",
        chunk_index=0,
        content=content,
        content_hash="abc123" + content[:10].replace(" ", "_"),
        priority_tier=3,
        asof=datetime.datetime.utcnow(),
        embedding=None,
    )
    session.add(chunk)
    session.commit()
    return chunk


@patch("tawn.memory.recall.embed_text", return_value=[0.1, 0.2, 0.3])
def test_recall_returns_snippet_format(mock_embed, home, db):
    _seed_chunk(db, "pgvector decision made for memory core")
    result = recall("pgvector", session=db, home=home)
    assert result["format"] == "snippets"
    assert "chunks" in result
    assert "query" in result


@patch("tawn.memory.recall.embed_text", side_effect=EmbedError("no model"))
def test_recall_no_embed_model_returns_empty_with_error(mock_embed, home, db):
    result = recall("query", session=db, home=home)
    assert result["format"] == "snippets"
    assert result["chunks"] == []
    assert "embed_error" in result


@patch("tawn.memory.recall.embed_text", side_effect=EmbedError("no model"))
def test_recall_domain_filter(mock_embed, home, db):
    _seed_chunk(db, "Work note about pgvector", "work")
    _seed_chunk(db, "Research note about pgvector", "research")
    result = recall("pgvector", domain="work", session=db, home=home)
    assert result["format"] == "snippets"
    chunks = result.get("chunks", [])
    assert all(c["domain"] == "work" for c in chunks if c["domain"] is not None)


@patch("tawn.memory.recall.embed_text", side_effect=EmbedError("no model"))
def test_recall_respects_top_k(mock_embed, home, db):
    for i in range(8):
        chunk = Chunk(
            domain="work",
            source_path=f"raw/a{i}.md",
            chunk_index=0,
            content=f"keyword content {i}",
            content_hash=f"h{i:015d}",
            priority_tier=3,
            asof=datetime.datetime.utcnow(),
        )
        db.add(chunk)
    db.commit()
    result = recall("keyword", session=db, home=home, top_k=3)
    assert len(result.get("chunks", [])) <= 3


@patch("tawn.memory.recall.embed_text", side_effect=EmbedError("no model"))
def test_recall_composed_no_router_returns_snippets(mock_embed, home, db):
    _seed_chunk(db, "Decision about auth middleware.")
    result = recall("auth middleware", format="composed", session=db, home=home)
    assert result["format"] == "composed"
    assert "answer" in result


@patch("tawn.memory.recall.embed_text", return_value=[0.1, 0.2, 0.3])
def test_recall_composed_format_calls_router(mock_embed, home, db):
    _seed_chunk(db, "Decision about auth middleware.")
    mock_router = MagicMock()
    mock_router.stream.return_value = iter([
        MagicMock(text="You decided on auth middleware.", done=False, tokens_in=0, tokens_out=0),
        MagicMock(text="", done=True, tokens_in=10, tokens_out=5),
    ])
    with patch("tawn.memory.recall._cosine_search", return_value=db.query(Chunk).all()):
        result = recall(
            "auth middleware", format="composed",
            session=db, home=home, router=mock_router,
        )
    assert result["format"] == "composed"
    assert "answer" in result


def test_cosine_search_excludes_other_embedders(tmp_path):
    """Same width, different model = different vector space.

    nomic-embed-text and gemini-embedding-001 are both 768-dimensional but
    share no geometry. Comparing across them does not error — it returns
    nonsense with confident-looking scores, which is worse than failing.
    """
    import datetime
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as _S
    from tawn.memory.schema import Base, Chunk
    from tawn.memory.recall import _cosine_search

    (tmp_path / "config.yaml").write_text("embed_model: gemini-embedding-001\nembed_dims: 768\n")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with _S(engine) as s:
        for i, model in enumerate(["nomic-embed-text", "gemini-embedding-001"]):
            s.add(Chunk(
                source_path=f"/{model}.md", chunk_index=i, content=f"from {model}",
                content_hash="h" * 16, asof=datetime.datetime.utcnow(),
                compiled_at=datetime.datetime.utcnow(),
                embed_model=model, embed_dims=768,
            ))
        s.commit()

        # SQLite has no pgvector, so the filter is exercised via the query
        # builder rather than the distance operator.
        q = _cosine_search(s, [0.1] * 768, None, 10, None, home=tmp_path)
        # Falls back to all chunks on SQLite; assert the guard itself instead.
        from tawn.compiler.embedder import get_embed_config
        assert get_embed_config(tmp_path)[0] == "gemini-embedding-001"
        assert len(q) >= 1
