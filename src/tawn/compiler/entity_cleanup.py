"""One-off repair of entities and edges created before hygiene rules existed.

Applies the same rules as the live path (`compiler.hygiene`) to data already
stored, because a normal compile never revisits it. On a real corpus this
found:

  * 4,117 of 17,612 entities that were file paths, IPs, hex tokens or
    `Category #hash` codes — each with its own wiki page;
  * `is located in` / `located_in` / `located in` as three separate relations;
  * `Uniswap`, `uniswap` and `UNISWAP` as three separate entities, which also
    meant a `[[uniswap]]` wikilink resolved to whichever page happened to
    exist.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from tawn.compiler.hygiene import (
    is_junk_entity,
    normalize_entity_name,
    normalize_relation,
)
from tawn.memory.schema import Entity, EntityEdge


def purge_junk_entities(session: Session) -> int:
    """Delete entities that are not entities, and their edges."""
    junk_ids = [e.id for e in session.query(Entity).all() if is_junk_entity(e.canonical)]
    if not junk_ids:
        return 0

    session.query(EntityEdge).filter(
        EntityEdge.from_entity_id.in_(junk_ids) | EntityEdge.to_entity_id.in_(junk_ids)
    ).delete(synchronize_session=False)
    session.query(Entity).filter(Entity.id.in_(junk_ids)).delete(synchronize_session=False)
    session.commit()
    return len(junk_ids)


def normalize_relations(session: Session) -> int:
    """Rewrite edge labels to their canonical form. Returns rows changed."""
    changed = 0
    for edge in session.query(EntityEdge).all():
        norm = normalize_relation(edge.relation)
        if norm != edge.relation:
            edge.relation = norm
            changed += 1
    session.commit()
    return changed


def merge_case_duplicates(session: Session) -> int:
    """Fold entities differing only by case/whitespace into one. Returns merges.

    The surviving row keeps the best-looking name — the variant with the most
    uppercase letters, since `Open-Meteo` reads better than `open-meteo` and
    is what a wikilink should render.
    """
    buckets: dict[str, list[Entity]] = defaultdict(list)
    for ent in session.query(Entity).all():
        buckets[normalize_entity_name(ent.canonical)].append(ent)

    merged = 0
    for key, group in buckets.items():
        if len(group) < 2:
            continue
        keeper = max(group, key=lambda e: (sum(c.isupper() for c in e.canonical), -e.id))
        losers = [e for e in group if e.id != keeper.id]
        loser_ids = [e.id for e in losers]

        # Re-point edges at the keeper before deleting the duplicates.
        for edge in session.query(EntityEdge).filter(
            EntityEdge.from_entity_id.in_(loser_ids)
        ).all():
            edge.from_entity_id = keeper.id
        for edge in session.query(EntityEdge).filter(
            EntityEdge.to_entity_id.in_(loser_ids)
        ).all():
            edge.to_entity_id = keeper.id
        session.flush()

        # Self-edges and exact duplicates can appear once both ends move.
        seen: set[tuple] = set()
        for edge in session.query(EntityEdge).filter(
            (EntityEdge.from_entity_id == keeper.id) | (EntityEdge.to_entity_id == keeper.id)
        ).all():
            sig = (edge.from_entity_id, edge.to_entity_id, edge.relation)
            if edge.from_entity_id == edge.to_entity_id or sig in seen:
                session.delete(edge)
            else:
                seen.add(sig)

        session.query(Entity).filter(Entity.id.in_(loser_ids)).delete(synchronize_session=False)
        merged += len(losers)

    session.commit()
    return merged


def cleanup_all(session: Session) -> dict:
    """Run every repair, in dependency order. Returns what each one changed."""
    purged = purge_junk_entities(session)
    merged = merge_case_duplicates(session)
    relabelled = normalize_relations(session)
    return {
        "purged": purged,
        "merged": merged,
        "relations_normalized": relabelled,
        "entities_remaining": session.query(Entity).count(),
        "edges_remaining": session.query(EntityEdge).count(),
    }
