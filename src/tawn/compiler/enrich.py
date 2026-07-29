"""Resumable LLM enrichment pass.

Deliberately NOT part of `run_compile`. A 26k-chunk corpus times one model
call each is hours of work; folding that into compile would reintroduce the
exact failure the 2026-07-23 batched-commit decision fixed, at larger scale —
one slow call stalling ingestion, a kill mid-run losing everything.

Compile stays fast and this pass catches up behind it, so a missing or broken
model degrades quality (cleaned text, co-occurrence edges) rather than
halting ingestion.

Runs locally by default: `sensitive=True` filters the router to local
providers before selection, which keeps a full rebuild free and private.
"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from sqlalchemy.orm import Session

from tawn.compiler.hygiene import is_junk_entity, normalize_entity_name, normalize_relation
from tawn.memory.schema import Chunk, ChunkGroup, Entity, EntityEdge

MAX_ATTEMPTS = 3

# Fallback edge label when a chunk names several entities but asserts no
# relation between them. Wording matters: it is rendered verbatim on wiki
# pages, so it reads as English rather than graph jargon.
MENTIONED_WITH = "mentioned with"

# Local models routinely wrap JSON in chatter ("Sure! Here you go: {...}").
# Salvaging the object is the difference between a working pass and one that
# burns every chunk's attempt budget on formatting noise.
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_CHUNK_PROMPT = """You are indexing one fragment of a person's memory.

Return ONLY a JSON object, no prose, with these keys:
  title     — under 60 characters, what this fragment is about
  summary   — one sentence, plain language, what it says
  entities  — array of proper nouns that matter (people, projects, tools,
              organisations). Omit generic words, error strings and code symbols.
  relations — array of [subject, relation, object] triples, using only names
              that appear in entities. Empty array if none are clear.

Fragment:
{content}
"""

_GROUP_PROMPT = """These are summaries of fragments from one document or conversation.

Return ONLY a JSON object with:
  title   — under 60 characters, naming the document or conversation
  summary — one sentence covering what it is about as a whole

Summaries:
{summaries}
"""


@dataclass
class EnrichResult:
    ok: bool
    chunks_enriched: int = 0
    groups_enriched: int = 0
    failed: int = 0
    error: str | None = None


def _parse_payload(text: str) -> dict | None:
    match = _JSON_RE.search(text or "")
    if not match:
        return None
    try:
        out = json.loads(match.group())
    except (json.JSONDecodeError, ValueError):
        return None
    return out if isinstance(out, dict) else None


def _default_client(home: Path):
    from tawn.model.router import default_router

    return default_router(home)


def _resolve_entity(session: Session, name: str, domain: str | None) -> Entity | None:
    """Find or create an entity, rejecting non-entities and folding case.

    Matching used to be case-sensitive and exact, so `Uniswap`, `uniswap` and
    `UNISWAP` became three separate entities with three separate wiki pages —
    and a `[[uniswap]]` link resolved to whichever happened to exist.
    """
    name = (name or "").strip()
    if is_junk_entity(name):
        return None

    key = normalize_entity_name(name)
    existing = next(
        (e for e in session.query(Entity).filter(Entity.canonical.ilike(name)).all()
         if normalize_entity_name(e.canonical) == key),
        None,
    )
    if existing is not None:
        existing.last_updated = datetime.datetime.utcnow()
        return existing

    ent = Entity(canonical=name, domain=domain)
    session.add(ent)
    session.flush()
    return ent


def _add_edge(session: Session, a: Entity, b: Entity, relation: str) -> None:
    """Record an edge, normalising the label so one relation is one label.

    The model phrases the same relation several ways — `is located in`,
    `located_in`, `located in` — which split 1,034 edges of one idea across
    three labels and stopped any relation type from grouping.
    """
    if a.id == b.id:
        return
    relation = normalize_relation(relation)
    edge = (
        session.query(EntityEdge)
        .filter_by(from_entity_id=a.id, to_entity_id=b.id, relation=relation)
        .first()
    )
    if edge is not None:
        edge.weight = (edge.weight or 1) + 1
    else:
        session.add(EntityEdge(
            from_entity_id=a.id, to_entity_id=b.id, relation=relation, weight=1,
        ))


def enrich_chunks(
    session: Session,
    home: Path,
    limit: int = 200,
    client=None,
    batch: int = 25,
    allow_cloud: bool = False,
) -> EnrichResult:
    """Enrich up to `limit` un-enriched chunks. Commits every `batch` rows.

    `allow_cloud=False` passes `sensitive=True`, which filters the router to
    local providers *before* selection — chunk contents never leave the
    machine. Opting in sends them to whichever cloud provider the router
    picks, so it is a deliberate per-call choice, never a default.
    """
    rows = (
        session.query(Chunk)
        .filter(Chunk.enriched_at.is_(None))
        .filter(Chunk.enrich_attempts < MAX_ATTEMPTS)
        .order_by(Chunk.priority_tier.asc(), Chunk.compiled_at.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return EnrichResult(ok=True)

    # End the read transaction before any network call.
    #
    # SQLAlchemy opens a transaction on first query and holds it until commit.
    # Model calls take seconds each and can hang indefinitely, so leaving that
    # transaction open pinned locks for the whole pass — one stalled request
    # sat `idle in transaction` for 6h20m and blocked every other writer,
    # including an unrelated maintenance job queued behind it.
    session.commit()

    try:
        client = client or _default_client(home)
    except Exception as exc:  # noqa: BLE001 — absence of a model is not an error here
        return EnrichResult(ok=False, error=f"no model available: {exc}")

    from tawn.model.types import Message

    enriched = failed = 0
    for i, chunk in enumerate(rows):
        prompt = _CHUNK_PROMPT.format(content=chunk.content[:4000])
        try:
            resp = client.complete(
                [Message(role="user", content=prompt)], sensitive=not allow_cloud
            )
        except Exception as exc:  # noqa: BLE001
            # A provider outage is not this chunk's fault. Stop the run rather
            # than burning every remaining chunk's attempt budget on it.
            session.commit()
            return EnrichResult(
                ok=False, chunks_enriched=enriched, failed=failed, error=str(exc),
            )

        payload = _parse_payload(resp.text)
        if payload is None:
            chunk.enrich_attempts = (chunk.enrich_attempts or 0) + 1
            failed += 1
        else:
            chunk.title = ((payload.get("title") or "").strip()[:200]) or None
            chunk.summary = ((payload.get("summary") or "").strip()) or None
            chunk.enriched_at = datetime.datetime.utcnow()

            ents: list[Entity] = []
            for name in (payload.get("entities") or [])[:20]:
                ent = _resolve_entity(session, str(name), chunk.domain)
                if ent is not None:
                    ents.append(ent)

            by_name = {e.canonical: e for e in ents}
            wrote_edge = False
            for triple in (payload.get("relations") or [])[:20]:
                if not (isinstance(triple, (list, tuple)) and len(triple) == 3):
                    continue
                subj, rel, obj = (str(x).strip() for x in triple)
                a, b = by_name.get(subj), by_name.get(obj)
                if a is not None and b is not None and rel:
                    _add_edge(session, a, b, rel[:60])
                    wrote_edge = True

            # A chunk naming several entities but asserting no relation still
            # tells us they belong together — better than an empty graph.
            if not wrote_edge and len(ents) > 1:
                for a, b in combinations(ents[:8], 2):
                    # Plain English rather than "co-occurs": this label is
                    # rendered straight onto entity pages a person reads.
                    _add_edge(session, a, b, MENTIONED_WITH)

            enriched += 1

        if (i + 1) % batch == 0:
            session.commit()

    session.commit()
    return EnrichResult(ok=True, chunks_enriched=enriched, failed=failed)


def enrich_groups(
    session: Session,
    home: Path,
    limit: int = 100,
    client=None,
    batch: int = 25,
    allow_cloud: bool = False,
) -> EnrichResult:
    """Roll each group up into the title and summary that heads its feed card."""
    groups = (
        session.query(ChunkGroup)
        .filter(ChunkGroup.enriched_at.is_(None))
        .filter(ChunkGroup.enrich_attempts < MAX_ATTEMPTS)
        .limit(limit)
        .all()
    )
    if not groups:
        return EnrichResult(ok=True)

    pending = []
    for grp in groups:
        summaries = [
            s for (s,) in session.query(Chunk.summary)
            .filter(Chunk.group_key == grp.group_key)
            .filter(Chunk.summary.isnot(None))
            .limit(30)
            .all()
        ]
        # Members not enriched yet — wait for the next pass rather than
        # spending an attempt on a prompt with nothing in it.
        if summaries:
            pending.append((grp, summaries))

    if not pending:
        return EnrichResult(ok=True)

    try:
        client = client or _default_client(home)
    except Exception as exc:  # noqa: BLE001
        return EnrichResult(ok=False, error=f"no model available: {exc}")

    from tawn.model.types import Message

    done = failed = 0
    for i, (grp, summaries) in enumerate(pending):
        prompt = _GROUP_PROMPT.format(
            summaries="\n".join(f"- {s}" for s in summaries)
        )
        try:
            resp = client.complete(
                [Message(role="user", content=prompt)], sensitive=not allow_cloud
            )
        except Exception as exc:  # noqa: BLE001
            session.commit()
            return EnrichResult(
                ok=False, groups_enriched=done, failed=failed, error=str(exc),
            )

        payload = _parse_payload(resp.text)
        if payload is None:
            grp.enrich_attempts = (grp.enrich_attempts or 0) + 1
            failed += 1
        else:
            grp.title = ((payload.get("title") or "").strip()[:200]) or grp.title
            grp.summary = ((payload.get("summary") or "").strip()) or None
            grp.enriched_at = datetime.datetime.utcnow()
            done += 1

        if (i + 1) % batch == 0:
            session.commit()

    session.commit()
    return EnrichResult(ok=True, groups_enriched=done, failed=failed)


def run_enrich(
    home: Path,
    session: Session | None = None,
    limit: int = 200,
    client=None,
    allow_cloud: bool = False,
) -> EnrichResult:
    """Chunk pass then group pass. Safe to call repeatedly; resumes where it stopped."""
    if session is None:
        from tawn.db import make_engine

        with Session(make_engine()) as s:
            return run_enrich(home, s, limit=limit, client=client, allow_cloud=allow_cloud)

    chunks = enrich_chunks(session, home, limit=limit, client=client, allow_cloud=allow_cloud)
    if not chunks.ok:
        return chunks

    groups = enrich_groups(session, home, client=client, allow_cloud=allow_cloud)
    return EnrichResult(
        ok=groups.ok,
        chunks_enriched=chunks.chunks_enriched,
        groups_enriched=groups.groups_enriched,
        failed=chunks.failed + groups.failed,
        error=groups.error,
    )
