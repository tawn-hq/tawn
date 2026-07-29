import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.compiler.entity_cleanup import (
    cleanup_all,
    merge_case_duplicates,
    normalize_relations,
    purge_junk_entities,
)
from tawn.memory.schema import Base, Entity, EntityEdge


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _ent(s, name, domain=None):
    e = Entity(canonical=name, domain=domain)
    s.add(e)
    s.flush()
    return e


def test_purges_junk_and_its_edges(db):
    good = _ent(db, "Clara")
    junk = _ent(db, "127.0.0.1")
    db.add(EntityEdge(from_entity_id=good.id, to_entity_id=junk.id, relation="uses"))
    db.commit()

    assert purge_junk_entities(db) == 1
    assert db.query(Entity).count() == 1
    assert db.query(EntityEdge).count() == 0


def test_normalizes_relation_labels(db):
    a, b = _ent(db, "A"), _ent(db, "B")
    db.add(EntityEdge(from_entity_id=a.id, to_entity_id=b.id, relation="IS_LOCATED_IN"))
    db.add(EntityEdge(from_entity_id=b.id, to_entity_id=a.id, relation="located in"))
    db.commit()

    normalize_relations(db)
    assert {e.relation for e in db.query(EntityEdge).all()} == {"located in"}


def test_merges_case_duplicates_and_keeps_best_casing(db):
    _ent(db, "uniswap")
    _ent(db, "Uniswap")
    _ent(db, "UNISWAP")
    db.commit()

    assert merge_case_duplicates(db) == 2
    assert db.query(Entity).one().canonical == "UNISWAP"


def test_merge_repoints_edges_at_the_survivor(db):
    keep = _ent(db, "Open-Meteo")
    dupe = _ent(db, "open-meteo")
    other = _ent(db, "Clara")
    db.add(EntityEdge(from_entity_id=other.id, to_entity_id=dupe.id, relation="uses"))
    db.commit()

    merge_case_duplicates(db)
    edge = db.query(EntityEdge).one()
    assert edge.to_entity_id == keep.id


def test_merge_drops_self_edges_created_by_folding(db):
    a = _ent(db, "Clara")
    b = _ent(db, "clara")
    db.add(EntityEdge(from_entity_id=a.id, to_entity_id=b.id, relation="uses"))
    db.commit()

    merge_case_duplicates(db)
    assert db.query(EntityEdge).count() == 0


def test_cleanup_all_reports_each_change(db):
    _ent(db, "Clara")
    _ent(db, "clara")
    _ent(db, "0xdeadbeef")
    db.commit()

    result = cleanup_all(db)
    assert result["purged"] == 1
    assert result["merged"] == 1
    assert result["entities_remaining"] == 1
