"""HTTP routes for the compiled wiki.

Paths resolve against the layout the compiler actually writes —
`wiki/<domain>/index.md` plus `wiki/entities/*.md` — not the
`wiki/domains/*.md` shape implied by the deleted full-corpus generator.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from tawn.db import get_session
from tawn.home import tawn_home
from tawn.memory.schema import Entity, EntityEdge

router = APIRouter(tags=["wiki"])

_MISSING = "wiki not generated yet — run `tawn compile`"

# Root-level directories that are not domains.
_NON_DOMAIN_DIRS = {"entities"}


def _wiki_dir() -> Path:
    return tawn_home() / "wiki"


@router.get("/tree")
def get_tree():
    """Domain pages and entity pages currently on disk."""
    wiki = _wiki_dir()
    if not wiki.is_dir():
        return {"domains": [], "entities": [], "ready": False}

    domains = [
        {"name": d.name, "path": f"{d.name}/index.md"}
        for d in sorted(wiki.iterdir())
        if d.is_dir()
        and not d.name.startswith(".")
        and d.name not in _NON_DOMAIN_DIRS
        and (d / "index.md").exists()
    ]
    ent_dir = wiki / "entities"
    entities = (
        [{"name": p.stem, "path": f"entities/{p.name}"} for p in sorted(ent_dir.glob("*.md"))]
        if ent_dir.is_dir()
        else []
    )
    return {"domains": domains, "entities": entities, "ready": True}


@router.get("/page")
def get_page(path: str = Query(..., description="Path relative to the wiki root")):
    """Raw markdown for one wiki page."""
    wiki = _wiki_dir()
    if not wiki.is_dir():
        raise HTTPException(404, _MISSING)

    # Resolve then assert containment — a bare join would happily serve
    # ../../etc/passwd.
    root = wiki.resolve()
    try:
        target = (root / path).resolve()
        target.relative_to(root)
    except (ValueError, OSError):
        raise HTTPException(400, "invalid path")

    if not target.is_file():
        raise HTTPException(404, f"page not found: {path} — run `tawn compile`")
    return {"path": path, "content": target.read_text(encoding="utf-8", errors="replace")}


@router.get("/entity/{name}")
def get_entity(name: str, session: Session = Depends(get_session)):
    """One entity with its outgoing links and its backlinks."""
    ent = session.query(Entity).filter(Entity.canonical == name).first()
    if ent is None:
        raise HTTPException(404, f"unknown entity: {name}")

    out_edges = session.query(EntityEdge).filter_by(from_entity_id=ent.id).all()
    in_edges = session.query(EntityEdge).filter_by(to_entity_id=ent.id).all()

    ids = {e.to_entity_id for e in out_edges} | {e.from_entity_id for e in in_edges}
    names = (
        {e.id: e.canonical for e in session.query(Entity).filter(Entity.id.in_(ids)).all()}
        if ids
        else {}
    )

    return {
        "id": ent.id,
        "canonical": ent.canonical,
        "domain": ent.domain,
        "confidence": ent.confidence,
        "first_seen": ent.first_seen.isoformat() if ent.first_seen else None,
        "related": [
            {"id": e.to_entity_id, "label": names.get(e.to_entity_id, "?"),
             "relation": e.relation, "weight": e.weight or 1}
            for e in out_edges if e.to_entity_id in names
        ],
        "backlinks": [
            {"id": e.from_entity_id, "label": names.get(e.from_entity_id, "?"),
             "relation": e.relation, "weight": e.weight or 1}
            for e in in_edges if e.from_entity_id in names
        ],
    }


@router.get("/graph")
def get_graph(
    domain: str | None = None,
    entity: str | None = None,
    depth: int = 1,
    limit: int = 300,
    cluster: bool = False,
    session: Session = Depends(get_session),
):
    """Nodes and links for the graph canvas.

    `cluster=true` adds per-domain counts so the root view can draw
    supernodes: cytoscape degrades past a few thousand nodes, and 8k
    entities at once would be an unreadable hairball regardless of speed.
    """
    if entity:
        root = session.query(Entity).filter(Entity.canonical == entity).first()
        if root is None:
            raise HTTPException(404, f"unknown entity: {entity}")
        keep = {root.id}
        frontier = {root.id}
        for _ in range(max(1, depth)):
            if not frontier:
                break
            edges = (
                session.query(EntityEdge)
                .filter(
                    EntityEdge.from_entity_id.in_(frontier)
                    | EntityEdge.to_entity_id.in_(frontier)
                )
                .all()
            )
            reached = {e.from_entity_id for e in edges} | {e.to_entity_id for e in edges}
            frontier = reached - keep
            keep |= reached
        ents = session.query(Entity).filter(Entity.id.in_(keep)).limit(limit).all()
    else:
        q = session.query(Entity)
        if domain:
            q = q.filter(Entity.domain == domain)
        ents = q.limit(limit).all()

    ids = {e.id for e in ents}
    edges = [
        ed
        for ed in session.query(EntityEdge).all()
        if ed.from_entity_id in ids and ed.to_entity_id in ids
    ]

    payload = {
        "nodes": [
            {"id": e.id, "label": e.canonical, "domain": e.domain,
             "confidence": e.confidence}
            for e in ents
        ],
        "links": [
            {"source": ed.from_entity_id, "target": ed.to_entity_id,
             "relation": ed.relation, "weight": ed.weight or 1}
            for ed in edges
        ],
    }
    if cluster:
        payload["clusters"] = [
            {"domain": d or "unassigned", "count": n}
            for d, n in session.query(Entity.domain, func.count(Entity.id))
            .group_by(Entity.domain)
            .all()
        ]
    return payload


@router.get("/links")
def get_links():
    """The generated links.json — the graph's file-backed data source."""
    path = _wiki_dir() / "links.json"
    if not path.is_file():
        raise HTTPException(404, _MISSING)
    return json.loads(path.read_text())
