"""Tests for the grouped feed endpoint."""

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tawn.memory.schema import Chunk, ChunkGroup
from tawn.web import create_app


def _client_for(db_engine):
    """Bind the app to the test engine.

    `Depends(get_session)` builds its own engine from settings, so without the
    override every request would hit the developer's real Postgres.
    """
    import tawn.db as db_mod

    def _get_session():
        with Session(db_engine) as s:
            yield s

    app = create_app(db_engine)
    app.dependency_overrides[db_mod.get_session] = _get_session
    return TestClient(app)


@pytest.fixture()
def client(tawn_home, db_engine):
    return _client_for(db_engine)


def _seed(db_engine):
    with Session(db_engine) as s:
        s.add(ChunkGroup(group_key="/g.md", title="Router work",
                         summary="Two decisions.", domain="work", chunk_count=2))
        for i in range(2):
            s.add(Chunk(
                source_path="/g.md", chunk_index=i, content=f"body {i}",
                content_hash="h" * 16, asof=datetime.datetime.utcnow(),
                compiled_at=datetime.datetime.utcnow(),
                domain="work", group_key="/g.md", group_label="g.md",
                title=f"t{i}", summary=f"s{i}",
            ))
        s.commit()


def test_groups_endpoint_returns_cards(client, db_engine):
    _seed(db_engine)
    body = client.get("/api/groups").json()

    assert body["total"] == 1
    card = body["groups"][0]
    assert card["title"] == "Router work"
    assert card["chunk_count"] == 2
    assert len(card["chunks"]) == 2
    assert card["chunks"][0]["title"] == "t0"


def test_groups_filter_by_domain(client, db_engine):
    _seed(db_engine)
    assert client.get("/api/groups", params={"domain": "work"}).json()["total"] == 1
    assert client.get("/api/groups", params={"domain": "wealth"}).json()["total"] == 0


def test_groups_empty_when_nothing_compiled(client):
    body = client.get("/api/groups").json()
    assert body["total"] == 0
    assert body["groups"] == []


def test_unenriched_chunk_falls_back_to_content(client, db_engine):
    """During backfill the feed must still read — cleaned text stands in."""
    with Session(db_engine) as s:
        s.add(ChunkGroup(group_key="/u.md", chunk_count=1))
        s.add(Chunk(
            source_path="/u.md", chunk_index=0,
            content="Raw but cleaned content about the router.",
            content_hash="h" * 16, asof=datetime.datetime.utcnow(),
            compiled_at=datetime.datetime.utcnow(),
            group_key="/u.md",
        ))
        s.commit()

    card = client.get("/api/groups").json()["groups"][0]
    assert card["enriched"] is False
    assert "Raw but cleaned content" in card["chunks"][0]["summary"]


def test_groups_paginate(client, db_engine):
    with Session(db_engine) as s:
        for i in range(5):
            s.add(ChunkGroup(group_key=f"/g{i}.md", chunk_count=1, domain="work"))
        s.commit()

    body = client.get("/api/groups", params={"limit": 2, "offset": 0}).json()
    assert body["total"] == 5
    assert len(body["groups"]) == 2


def test_card_summary_is_readable_prose_not_pipe_soup(client, db_engine):
    """Unenriched cards fell back to a raw slice: tables became `| a | b |`."""
    import datetime

    with Session(db_engine) as s:
        s.add(ChunkGroup(group_key="/t.md", chunk_count=1))
        s.add(Chunk(
            source_path="/t.md", chunk_index=0,
            content="## Status Legend\n\n| Symbol | Meaning |\n|--------|---------|\n| OK | Implemented and functional |",
            content_hash="h" * 16, asof=datetime.datetime.utcnow(),
            compiled_at=datetime.datetime.utcnow(), group_key="/t.md",
        ))
        s.commit()

    card = client.get("/api/groups").json()["groups"][0]
    assert "|" not in (card["summary"] or "")
    assert "Status Legend" in card["summary"]
    assert "|" not in card["chunks"][0]["summary"]


def test_group_rollup_summary_wins_over_fallback(client, db_engine):
    import datetime

    with Session(db_engine) as s:
        s.add(ChunkGroup(group_key="/r.md", chunk_count=1, summary="The real roll-up."))
        s.add(Chunk(
            source_path="/r.md", chunk_index=0, content="Raw fallback text here.",
            content_hash="h" * 16, asof=datetime.datetime.utcnow(),
            compiled_at=datetime.datetime.utcnow(), group_key="/r.md",
        ))
        s.commit()

    assert client.get("/api/groups").json()["groups"][0]["summary"] == "The real roll-up."


def test_group_document_reassembles_in_order(client, db_engine):
    """Chunks are for retrieval; the document is for reading."""
    import datetime

    with Session(db_engine) as s:
        s.add(ChunkGroup(group_key="/d.md", chunk_count=2, title="The Doc"))
        for i, text in enumerate(["First part here.", "Second part here."]):
            s.add(Chunk(
                source_path="/d.md", chunk_index=i, content=text,
                content_hash="h" * 16, asof=datetime.datetime.utcnow(),
                compiled_at=datetime.datetime.utcnow(), group_key="/d.md",
            ))
        s.commit()

    body = client.get("/api/groups/document", params={"group_key": "/d.md"}).json()
    assert body["title"] == "The Doc"
    assert body["chunk_count"] == 2
    assert body["body"].index("First part") < body["body"].index("Second part")


def test_group_document_404_for_unknown_group(client):
    r = client.get("/api/groups/document", params={"group_key": "/nope.md"})
    assert r.status_code == 404


def test_notes_list_edit_and_delete(client, tawn_home):
    from tawn.memory.note import note

    note("Original note text.", home=tawn_home)
    listed = client.get("/api/notes").json()
    assert listed["total"] == 1
    nid = listed["notes"][0]["id"]

    edited = client.put(f"/api/notes/{nid}", json={"body": "Revised note text."}).json()
    assert edited["body"] == "Revised note text."

    assert client.delete(f"/api/notes/{nid}").json()["ok"] is True
    assert client.get("/api/notes").json()["total"] == 0


def test_edit_unknown_note_404(client, tawn_home):
    assert client.put("/api/notes/nope", json={"body": "x"}).status_code == 404


def test_enrich_status_reports_progress(client, db_engine):
    import datetime

    with Session(db_engine) as s:
        s.add(Chunk(
            source_path="/e.md", chunk_index=0, content="text",
            content_hash="h" * 16, asof=datetime.datetime.utcnow(),
            compiled_at=datetime.datetime.utcnow(),
        ))
        s.commit()

    body = client.get("/api/enrich/status").json()
    assert body["chunks_total"] == 1
    assert body["pending"] == 1


def test_enrich_endpoint_runs_bounded_pass(client, monkeypatch):
    from tawn.compiler.enrich import EnrichResult

    monkeypatch.setattr(
        "tawn.compiler.enrich.run_enrich",
        lambda home, session=None, limit=200, client=None, allow_cloud=False: EnrichResult(
            ok=True, chunks_enriched=3, groups_enriched=1
        ),
    )
    body = client.post("/api/enrich", json={"limit": 10}).json()
    assert body["ok"] is True
    assert body["chunks_enriched"] == 3
