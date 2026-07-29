"""Tests for the resumable LLM enrichment pass.

The model client is injected rather than mocked at the HTTP layer, following
the 2026-07-07 decision to inject SDK clients (fakes, no respx for these).
"""

import datetime
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.memory.schema import Base, Chunk, ChunkGroup, Entity, EntityEdge
from tawn.model.types import ModelResponse


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def home(tmp_path):
    return tmp_path


class FakeClient:
    """Stands in for a Router. Returns queued payloads in order."""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def complete(self, msgs, sensitive=False):
        self.calls += 1
        body = self.payloads.pop(0) if self.payloads else "{}"
        if isinstance(body, Exception):
            raise body
        return ModelResponse(text=body, model="fake", provider="fake")


def _chunk(s, **kw):
    c = Chunk(
        source_path=kw.pop("source_path", "/x.md"),
        chunk_index=kw.pop("chunk_index", 0),
        content=kw.pop("content", "We chose pgvector for semantic search."),
        content_hash="h" * 16,
        asof=datetime.datetime.utcnow(),
        **kw,
    )
    s.add(c)
    s.flush()
    return c


def test_enriches_chunk_with_title_summary_entities(home, db):
    from tawn.compiler.enrich import enrich_chunks

    payload = json.dumps({
        "title": "Chose pgvector",
        "summary": "Settled on pgvector for the semantic search layer.",
        "entities": ["pgvector", "Tawn"],
        "relations": [["Tawn", "uses", "pgvector"]],
    })
    c = _chunk(db)
    res = enrich_chunks(db, home, client=FakeClient([payload]))
    db.commit()

    assert res.chunks_enriched == 1
    got = db.get(Chunk, c.id)
    assert got.title == "Chose pgvector"
    assert got.summary.startswith("Settled on pgvector")
    assert got.enriched_at is not None
    assert {e.canonical for e in db.query(Entity).all()} == {"pgvector", "Tawn"}
    assert db.query(EntityEdge).count() == 1
    assert db.query(EntityEdge).one().relation == "uses"


def test_malformed_json_increments_attempts_not_enriched(home, db):
    from tawn.compiler.enrich import enrich_chunks

    c = _chunk(db)
    res = enrich_chunks(db, home, client=FakeClient(["not json at all"]))
    db.commit()

    assert res.failed == 1
    got = db.get(Chunk, c.id)
    assert got.enriched_at is None
    assert got.enrich_attempts == 1


def test_attempt_cap_stops_reselection(home, db):
    from tawn.compiler.enrich import MAX_ATTEMPTS, enrich_chunks

    _chunk(db, enrich_attempts=MAX_ATTEMPTS)
    client = FakeClient(["{}"])
    enrich_chunks(db, home, client=client)
    assert client.calls == 0


def test_provider_absent_returns_not_ok_without_raising(home, db):
    from tawn.compiler.enrich import enrich_chunks

    class Dead:
        def complete(self, msgs, sensitive=False):
            raise RuntimeError("no provider configured")

    _chunk(db)
    res = enrich_chunks(db, home, client=Dead())
    assert res.ok is False
    assert res.error


def test_cooccurrence_fallback_when_no_relations(home, db):
    from tawn.compiler.enrich import enrich_chunks

    payload = json.dumps({
        "title": "t", "summary": "s",
        "entities": ["Alpha", "Beta"], "relations": [],
    })
    _chunk(db)
    enrich_chunks(db, home, client=FakeClient([payload]))
    db.commit()

    edge = db.query(EntityEdge).one()
    assert edge.relation == "mentioned with"


def test_repeated_pairing_increments_weight(home, db):
    from tawn.compiler.enrich import enrich_chunks

    payload = json.dumps({
        "title": "t", "summary": "s",
        "entities": ["Alpha", "Beta"], "relations": [],
    })
    _chunk(db, chunk_index=0)
    _chunk(db, chunk_index=1, content="Alpha and Beta again.")
    enrich_chunks(db, home, client=FakeClient([payload, payload]))
    db.commit()

    assert db.query(EntityEdge).one().weight == 2


def test_salvages_json_wrapped_in_prose(home, db):
    """Local models routinely wrap JSON in chatter — that must not count as failure."""
    from tawn.compiler.enrich import enrich_chunks

    wrapped = 'Sure! Here you go:\n{"title": "T", "summary": "S", "entities": [], "relations": []}\nHope that helps.'
    c = _chunk(db)
    res = enrich_chunks(db, home, client=FakeClient([wrapped]))
    db.commit()

    assert res.chunks_enriched == 1
    assert db.get(Chunk, c.id).title == "T"


def test_group_rollup_writes_title_and_summary(home, db):
    from tawn.compiler.enrich import enrich_groups

    payload = json.dumps({"title": "Router work", "summary": "Two decisions about routing."})
    _chunk(db, group_key="/g.md", title="a", summary="sa",
           enriched_at=datetime.datetime.utcnow())
    db.add(ChunkGroup(group_key="/g.md", chunk_count=1))
    db.commit()

    res = enrich_groups(db, home, client=FakeClient([payload]))
    db.commit()

    assert res.groups_enriched == 1
    grp = db.get(ChunkGroup, "/g.md")
    assert grp.title == "Router work"
    assert grp.enriched_at is not None


def test_group_rollup_skips_groups_with_unenriched_members(home, db):
    """A group whose chunks have no summaries yet must wait, not burn an attempt."""
    from tawn.compiler.enrich import enrich_groups

    _chunk(db, group_key="/g.md")  # no summary
    db.add(ChunkGroup(group_key="/g.md", chunk_count=1))
    db.commit()

    client = FakeClient(["{}"])
    enrich_groups(db, home, client=client)
    assert client.calls == 0
    assert db.get(ChunkGroup, "/g.md").enrich_attempts == 0


def test_run_enrich_does_both_passes(home, db):
    from tawn.compiler.enrich import run_enrich

    chunk_payload = json.dumps({
        "title": "T", "summary": "S", "entities": ["Alpha"], "relations": [],
    })
    group_payload = json.dumps({"title": "G", "summary": "GS"})
    _chunk(db, group_key="/g.md")
    db.add(ChunkGroup(group_key="/g.md", chunk_count=1))
    db.commit()

    res = run_enrich(home, db, client=FakeClient([chunk_payload, group_payload]))
    db.commit()

    assert res.chunks_enriched == 1
    assert res.groups_enriched == 1
    assert db.get(ChunkGroup, "/g.md").title == "G"


def test_no_work_returns_ok(home, db):
    from tawn.compiler.enrich import enrich_chunks

    res = enrich_chunks(db, home, client=FakeClient([]))
    assert res.ok is True
    assert res.chunks_enriched == 0


# ── Cloud opt-in ──────────────────────────────────────────────────────────────

class RecordingClient(FakeClient):
    """Captures the `sensitive` flag each call was made with."""

    def __init__(self, payloads):
        super().__init__(payloads)
        self.sensitive_flags = []

    def complete(self, msgs, sensitive=False):
        self.sensitive_flags.append(sensitive)
        return super().complete(msgs, sensitive=sensitive)


def test_local_only_by_default_marks_calls_sensitive(home, db):
    """sensitive=True filters the router to local providers before selection."""
    from tawn.compiler.enrich import enrich_chunks

    _chunk(db)
    client = RecordingClient([json.dumps({"title": "t", "summary": "s"})])
    enrich_chunks(db, home, client=client)
    assert client.sensitive_flags == [True]


def test_allow_cloud_unsets_sensitive(home, db):
    from tawn.compiler.enrich import enrich_chunks

    _chunk(db)
    client = RecordingClient([json.dumps({"title": "t", "summary": "s"})])
    enrich_chunks(db, home, client=client, allow_cloud=True)
    assert client.sensitive_flags == [False]


def test_run_enrich_propagates_allow_cloud(home, db):
    from tawn.compiler.enrich import run_enrich

    _chunk(db, group_key="/g.md")
    db.add(ChunkGroup(group_key="/g.md", chunk_count=1))
    db.commit()

    client = RecordingClient([
        json.dumps({"title": "t", "summary": "s"}),
        json.dumps({"title": "g", "summary": "gs"}),
    ])
    run_enrich(home, db, client=client, allow_cloud=True)
    assert client.sensitive_flags == [False, False]


def test_read_transaction_is_released_before_model_calls(home, db, monkeypatch):
    """A hung model call must not pin database locks.

    `enrich_chunks` kept its read transaction open across model calls, so one
    stalled request sat idle-in-transaction for 6h20m and blocked every other
    writer. The fetch must be committed before any network work begins.
    """
    commits: list[str] = []
    real_commit = db.commit

    def tracking_commit():
        commits.append("commit")
        return real_commit()

    monkeypatch.setattr(db, "commit", tracking_commit)

    calls: list[str] = []

    class Recorder:
        def complete(self, msgs, sensitive=False):
            calls.append("model")
            return ModelResponse(
                text=json.dumps({"title": "t", "summary": "s"}),
                model="fake", provider="fake",
            )

    _chunk(db)
    db.commit()
    commits.clear()

    from tawn.compiler.enrich import enrich_chunks
    enrich_chunks(db, home, client=Recorder())

    assert commits, "expected a commit"
    assert calls, "expected a model call"
    # The decisive property: a commit lands before the first model call.
    assert commits[0] == "commit"
