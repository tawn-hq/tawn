"""Compiler orchestrator — 9-phase incremental compile pass.

Phases:
  1. Delta detection
  2. Parse new/changed files
  3. Conflict resolution
  4. Entity resolution
  5. Embed chunks
  6. Write chunks (UPSERT)
  7. TTL pass (mark stale, hard-delete expired)
  8. Wiki generation
  9. State update + compile_log

Public API
----------
run_compile(home, session, router=None, rebuild=False)  -> CompileResult
request_compile(home)                                    -> None
should_compile(home, quiet_seconds=30)                   -> bool
compile_status(home, session)                            -> dict
"""

from __future__ import annotations

import datetime
import os
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from tawn.compiler.classifier import classify
from tawn.compiler.conflicts import resolve_conflicts
from tawn.compiler.delta import _IGNORE_DIRS, scan_granted, scan_history, scan_raw, update_file_state
from tawn.ignore import load_ignore_patterns, should_ignore as _should_ignore
from tawn.compiler.embedder import EmbedError, embed_texts
from tawn.compiler.entities import extract_and_resolve
from tawn.compiler.parser import ParsedChunk, parse_file
from tawn.compiler.wiki import atomic_swap, generate_domain_index
from tawn.memory.schema import Chunk, ChunkGroup, CompileLog, Entity, EntityEdge, FileState

_SENTINEL = ".compile-requested"

# How many chunks go to the embedder per provider call. Batching amortises the
# per-request round trip (~2x at 8 on nomic-embed-text); a modest group bounds
# how much work a single failed call has to redo.
EMBED_GROUP = 32

# How many chunks are written between commits. Progress must be durable during
# a long run, not only at the end — see the 2026-07-23 batched-commit decision.
WRITE_BATCH = 200


def _storable_embedding(vec: list[float] | None) -> list[float] | None:
    """Return None on SQLite (Text column can't store vectors)."""
    if vec is None:
        return None
    from tawn.config import settings as _settings
    db_url = os.environ.get("TAWN_DB_URL") or _settings().db_url
    if "postgresql" not in db_url:
        return None
    return vec


@dataclass
class CompileResult:
    ok: bool
    files_processed: int = 0
    chunks_added: int = 0
    chunks_removed: int = 0
    entities_resolved: int = 0
    error: str | None = None


def request_compile(home: Path) -> None:
    """Touch the sentinel file to schedule a compile."""
    (home / _SENTINEL).touch()


def should_compile(home: Path, quiet_seconds: int = 30) -> bool:
    """Return True if sentinel exists and is older than quiet_seconds."""
    sentinel = home / _SENTINEL
    if not sentinel.exists():
        return False
    age = time.time() - sentinel.stat().st_mtime
    return age >= quiet_seconds


def compile_status(home: Path, session: Session | None = None) -> dict:
    """Return last compile time and whether a compile is pending."""
    last_compiled: str | None = None
    if session is not None:
        log = (
            session.query(CompileLog)
            .filter(CompileLog.ok.is_(True))
            .order_by(CompileLog.finished_at.desc())
            .first()
        )
        if log and log.finished_at:
            last_compiled = log.finished_at.isoformat()
    return {
        "last_compiled": last_compiled,
        "pending": (home / _SENTINEL).exists(),
    }


def run_compile(
    home: Path,
    session: Session | None = None,
    router=None,
    rebuild: bool = False,
) -> CompileResult:
    """Run a full (or rebuild) compile pass. Returns CompileResult."""
    if session is None:
        from tawn.db import make_engine
        engine = make_engine()
        with Session(engine) as s:
            return run_compile(home, s, router=router, rebuild=rebuild)

    started_at = datetime.datetime.utcnow()
    log_row = CompileLog(started_at=started_at)
    session.add(log_row)
    session.flush()

    raw_dir = home / "raw"
    wiki_dir = home / "wiki"
    staging_dir = wiki_dir / ".staging"
    review_dir = raw_dir / "review-queue"

    try:
        # load grants for external path scanning
        from tawn.capability.grants import Grants
        grants = Grants.load(home / "grants.yaml")
        granted_read = list(grants.read)

        # Phase 0 — Purge chunks from ignored paths (venvs, node_modules, user rules)
        _dir_segs, _glob_pats, _abs_paths = load_ignore_patterns(home)
        all_source_paths = [row[0] for row in session.query(Chunk.source_path).distinct().all()]
        purge_paths = {
            p for p in all_source_paths
            if _should_ignore(Path(p), _dir_segs, _glob_pats, _abs_paths)
            # Structural ignores too, so installs that indexed review-queue
            # before it was excluded get cleaned on the next ordinary compile
            # rather than needing a full rebuild.
            or _IGNORE_DIRS.intersection(Path(p).parts)
        }
        if purge_paths:
            session.query(Chunk).filter(Chunk.source_path.in_(purge_paths)).delete(synchronize_session=False)
            session.query(FileState).filter(FileState.path.in_(purge_paths)).delete(synchronize_session=False)
            session.flush()

        # Phase 1 — Delta detection (raw/ + granted paths + history)
        if rebuild:
            session.query(Chunk).delete()
            session.query(FileState).delete()
            # Entities and edges go too: a rebuild re-derives them under the
            # current extraction rules, and keeping rows produced by older
            # rules leaves a half-migrated graph that no pass will ever clean.
            session.query(EntityEdge).delete()
            session.query(Entity).delete()
            session.query(ChunkGroup).delete()
            session.flush()
            _text_exts = {".md", ".txt", ".rst"}
            # _IGNORE_DIRS applies here too — rebuild globs raw/ directly and
            # would otherwise re-ingest exactly what the incremental scan skips.
            delta_files_new = (
                [
                    f for f in raw_dir.rglob("*")
                    if f.is_file()
                    and f.suffix.lower() in _text_exts
                    and not _IGNORE_DIRS.intersection(f.parts)
                ]
                if raw_dir.exists() else []
            )
            # also include granted paths and history in rebuild
            for root in granted_read:
                root = root.expanduser().resolve()
                if root.exists():
                    glob = root.rglob("*") if root.is_dir() else [root]
                    delta_files_new += [f for f in glob if f.is_file() and f.suffix.lower() in _text_exts]
            hist_dir = home / "history"
            if hist_dir.exists():
                delta_files_new += list(hist_dir.glob("*.jsonl"))
            # agent memory: Claude Code project memory files
            from tawn.home import agent_memory_root
            _claude_projects = agent_memory_root()
            if _claude_projects.exists():
                _text_exts2 = {".md", ".txt", ".rst"}
                for _mem_dir in _claude_projects.glob("*/memory"):
                    if _mem_dir.is_dir():
                        delta_files_new += [
                            f for f in _mem_dir.rglob("*")
                            if f.is_file() and f.suffix.lower() in _text_exts2
                            and f.name != "MEMORY.md"
                        ]
            delta_files_changed: list[Path] = []
            delta_files_deleted: list[Path] = []
        else:
            from tawn.compiler.delta import DeltaResult, scan_agent_memory
            raw_delta = scan_raw(raw_dir, session)
            granted_delta = scan_granted(granted_read, session, home=home)
            history_delta = scan_history(home, session)
            agent_mem_delta = scan_agent_memory(session)
            delta_files_new = raw_delta.new + granted_delta.new + history_delta.new + agent_mem_delta.new
            delta_files_changed = raw_delta.changed + granted_delta.changed + history_delta.changed + agent_mem_delta.changed
            delta_files_deleted = raw_delta.deleted  # only hard-delete from raw/

        files_to_process = delta_files_new + delta_files_changed
        files_processed = len(files_to_process)

        # Phase 2 — Parse (with domain classification for external files)
        raw_str = str(raw_dir)
        hist_str = str(home / "history")
        all_chunks: list[ParsedChunk] = []
        from tawn.home import agent_memory_root
        agent_mem_prefix = str(agent_memory_root())
        for path in files_to_process:
            try:
                path_str = str(path)
                # classify domain for files outside raw/ (i.e. granted paths + history)
                inferred_domain: str | None = None
                if not path_str.startswith(raw_str) and not path_str.startswith(hist_str):
                    if path_str.startswith(agent_mem_prefix) and "/memory/" in path_str:
                        # Agent memory files are always work-domain project context
                        inferred_domain = "work"
                    else:
                        try:
                            content_preview = path.read_text(encoding="utf-8", errors="replace")[:2000]
                            inferred_domain = classify(path, content_preview)
                        except Exception:
                            pass
                chunks = parse_file(path, domain=inferred_domain, home=home)
                # for history chunks: run classifier on content for domain
                if path_str.startswith(hist_str):
                    for chunk in chunks:
                        if not chunk.frontmatter.get("domain"):
                            d = classify(path, chunk.content)
                            if d:
                                chunk.frontmatter["domain"] = d
                all_chunks.extend(chunks)
            except Exception:
                pass

        # Phase 3 — Conflict resolution
        resolved_chunks = resolve_conflicts(all_chunks, wiki_dir=wiki_dir)

        # Phase 4 — Entity resolution (skip federation/history/agent-memory imports)
        # These are high-volume, unstructured — entity extraction is quadratic
        # and adds no signal. Only run on raw/ (curated) documents.
        raw_str_prefix = str(raw_dir)
        import_str = str(raw_dir / "imports")
        hist_prefix = str(home / "history")
        agent_mem_prefix = str(agent_memory_root())
        structured_chunks = [
            c for c in resolved_chunks
            if (c.source_path.startswith(raw_str_prefix)
                and not c.source_path.startswith(import_str)
                and not c.source_path.startswith(hist_prefix))
            and not c.source_path.startswith(agent_mem_prefix)
        ]
        review_dir.mkdir(parents=True, exist_ok=True)
        with session.no_autoflush:
            entities_resolved = extract_and_resolve(structured_chunks, session, review_dir)

        # Phase 5+6 — Embed + write chunks
        # Preload all existing chunks for the files being compiled (bulk lookup
        # avoids N+1 queries — one SELECT per chunk in the naive approach).
        source_paths_in_batch = {p.source_path for p in resolved_chunks}
        existing_chunks: dict[tuple[str, int], Chunk] = {}
        if source_paths_in_batch:
            with session.no_autoflush:
                rows = (
                    session.query(Chunk)
                    .filter(Chunk.source_path.in_(source_paths_in_batch))
                    .all()
                )
            existing_chunks = {(r.source_path, r.chunk_index): r for r in rows}

        chunks_added = 0
        embed_available = True
        # A provider has never been confirmed working (embed_dims never
        # locked in config.yaml) → the very first failure means "no provider
        # configured at all" (missing key / no Ollama model), which fails
        # identically every time — one attempt, then stop for the rest of
        # the run. Once a provider IS confirmed (dims locked from a past
        # successful compile), failures are far more likely a transient
        # network blip, so those get retried with backoff instead of
        # poisoning the whole remaining batch on one bad connection.
        from tawn.compiler.embedder import get_embed_config as _get_embed_config
        _locked_model, _locked_dims = _get_embed_config(home)
        _provider_confirmed = _locked_dims > 0
        _EMBED_RETRIES = 3 if _provider_confirmed else 1
        _EMBED_BACKOFF_S = 2.0
        now = datetime.datetime.utcnow()

        # Decide what actually needs embedding *before* calling the embedder.
        # This loop used to embed every chunk unconditionally and only then
        # check whether the content had changed — so an incremental compile
        # with no edits still paid for the whole corpus and discarded the
        # result. At ~1.3s per chunk that was hours of pure waste per run.
        _needs_embed: list[ParsedChunk] = []
        for parsed in resolved_chunks:
            prior = existing_chunks.get((parsed.source_path, parsed.chunk_index))
            if (
                prior is not None
                and prior.content_hash == parsed.content_hash
                and prior.embedding is not None
                # A vector from a different embedder is not comparable, so it
                # must be redone even though the text is unchanged. Matching
                # on width alone is not enough — nomic-embed-text and
                # gemini-embedding-001 are both 768-dimensional but occupy
                # unrelated vector spaces, so a width check would silently
                # keep stale vectors and leave recall comparing nonsense.
                and (not _locked_dims or prior.embed_dims == _locked_dims)
                and (not _locked_model or prior.embed_model == _locked_model)
            ):
                continue
            _needs_embed.append(parsed)

        _embeddings: dict[tuple[str, int], tuple[list[float], str, int]] = {}

        def _embed_window(window: list[ParsedChunk]) -> bool:
            """Embed one window into `_embeddings`. False if the provider died."""
            nonlocal _provider_confirmed, _EMBED_RETRIES, embed_available
            for attempt in range(_EMBED_RETRIES):
                try:
                    vecs, model_name, dims = embed_texts(
                        [p.content for p in window], home
                    )
                    for p, vec in zip(window, vecs):
                        _embeddings[(p.source_path, p.chunk_index)] = (
                            vec, model_name, dims,
                        )
                    if not _provider_confirmed:
                        _provider_confirmed = True
                        _EMBED_RETRIES = 3
                    return True
                except EmbedError:
                    if attempt < _EMBED_RETRIES - 1:
                        time.sleep(_EMBED_BACKOFF_S * (2 ** attempt))
            if not _provider_confirmed:
                embed_available = False
                return False
            return True

        # Embedding is interleaved with writing, one _BATCH slice at a time,
        # so `session.commit()` below keeps firing *during* the embed phase.
        # Hoisting all embedding into a single pre-pass was faster to read but
        # reintroduced the failure the 2026-07-23 batched-commit decision
        # fixed: nothing durable, and no progress signal, until every vector
        # was computed — on a 12k-chunk rebuild that is an hour of work a
        # single Ctrl-C throws away, with 12k vectors held in memory meanwhile.
        # `_needs_embed` is already in `resolved_chunks` order, so a single
        # cursor walks it — no rescanning the batch per chunk.
        _embed_cursor = 0

        for i, parsed in enumerate(resolved_chunks):
            key = (parsed.source_path, parsed.chunk_index)
            if embed_available and key not in _embeddings:
                while _embed_cursor < len(_needs_embed) and key not in _embeddings:
                    window = _needs_embed[_embed_cursor:_embed_cursor + EMBED_GROUP]
                    _embed_cursor += len(window)
                    if not _embed_window(window):
                        break  # provider gone — rest stores unembedded

            _meta = _embeddings.get((parsed.source_path, parsed.chunk_index))
            embedding: list[float] | None = _meta[0] if _meta else None
            embed_model: str | None = _meta[1] if _meta else None
            embed_dims: int | None = _meta[2] if _meta else None

            safe_content = parsed.content.replace("\x00", "")
            existing = existing_chunks.get((parsed.source_path, parsed.chunk_index))
            if existing:
                if existing.content_hash != parsed.content_hash:
                    existing.content = safe_content
                    existing.content_hash = parsed.content_hash
                    existing.priority_tier = parsed.priority_tier
                    existing.asof = parsed.asof
                    existing.ttl_days = parsed.ttl_days
                    existing.stale = False
                    existing.compiled_at = now
                    existing.group_key = parsed.group_key
                    existing.group_label = parsed.group_label
                    # Content changed, so the old title/summary describe text
                    # that no longer exists — clear them for re-enrichment.
                    existing.title = None
                    existing.summary = None
                    existing.enriched_at = None
                    existing.enrich_attempts = 0
                    if embedding is not None:
                        existing.embedding = _storable_embedding(embedding)
                        existing.embed_model = embed_model
                        existing.embed_dims = embed_dims
            else:
                session.add(Chunk(
                    domain=parsed.frontmatter.get("domain") or parsed.frontmatter.get("inferred_domain"),
                    source_path=parsed.source_path,
                    chunk_index=parsed.chunk_index,
                    content=safe_content,
                    embedding=_storable_embedding(embedding),
                    content_hash=parsed.content_hash,
                    priority_tier=parsed.priority_tier,
                    asof=parsed.asof,
                    ttl_days=parsed.ttl_days,
                    stale=False,
                    compiled_at=now,
                    group_key=parsed.group_key,
                    group_label=parsed.group_label,
                    embed_model=embed_model,
                    embed_dims=embed_dims,
                ))
                chunks_added += 1

            # Commit in batches — not just flush. Each chunk here can involve
            # a real, slow, network-dependent embed call; a single-transaction
            # whole-run commit means one bad connection anywhere in a
            # multi-thousand-chunk run holds *everything* processed so far
            # hostage (invisible to any other session, and lost entirely if
            # the process is killed). Committing periodically makes embedded
            # chunks durable and searchable as they land, not all-or-nothing.
            if (i + 1) % WRITE_BATCH == 0:
                session.commit()

        # Refresh ChunkGroup rows for every group touched this run. Counts are
        # denormalised so the feed can render a card header without a GROUP BY
        # over the whole chunks table on every page load.
        from sqlalchemy import func as _func

        touched = {p.group_key for p in resolved_chunks if p.group_key}
        for gkey in touched:
            rows = (
                session.query(Chunk.domain, _func.count(Chunk.id))
                .filter(Chunk.group_key == gkey)
                .group_by(Chunk.domain)
                .all()
            )
            total = sum(n for _, n in rows)
            dominant = max(rows, key=lambda r: r[1])[0] if rows else None
            label = next(
                (p.group_label for p in resolved_chunks if p.group_key == gkey), None
            )
            grp = session.get(ChunkGroup, gkey)
            if grp is None:
                session.add(ChunkGroup(
                    group_key=gkey, domain=dominant, chunk_count=total, title=label,
                ))
            else:
                grp.chunk_count = total
                grp.domain = dominant
        session.flush()

        # Remove chunks for deleted files
        chunks_removed = 0
        for deleted_path in delta_files_deleted:
            rows = session.query(Chunk).filter_by(source_path=str(deleted_path)).all()
            for row in rows:
                session.delete(row)
                chunks_removed += 1
            session.query(FileState).filter_by(path=str(deleted_path)).delete()

        # Phase 7 — TTL pass
        now = datetime.datetime.utcnow()
        for chunk in session.query(Chunk).filter(Chunk.ttl_days.isnot(None)).all():
            if chunk.asof is None:
                continue
            age_days = (now - chunk.asof).days
            if age_days >= (chunk.ttl_days * 2):
                session.delete(chunk)
            elif age_days >= chunk.ttl_days:
                chunk.stale = True

        session.flush()

        # Phase 8 — Wiki generation per changed domain
        staging_dir.mkdir(parents=True, exist_ok=True)
        # Every domain that has chunks, not only those touched this run.
        # Scoping to `resolved_chunks` meant a compile with nothing changed
        # staged no domain pages at all — and the prune below then deleted
        # every live one, so all four domain indexes vanished after an
        # uneventful compile.
        live_domains = {
            d for (d,) in session.query(Chunk.domain).filter(Chunk.domain.isnot(None)).distinct().all()
            if d
        }

        for domain in sorted(live_domains):
            entities = [
                e.canonical
                for e in session.query(Entity).filter_by(domain=domain).limit(20).all()
            ]
            recent = [
                c.content[:200]
                for c in session.query(Chunk)
                .filter_by(domain=domain)
                .order_by(Chunk.compiled_at.desc())
                .limit(10)
                .all()
            ]
            generate_domain_index(domain, entities, recent, wiki_dir, staging_dir, router)

        # Entity pages + link index. Related/backlink maps are built in one
        # pass over the edge table rather than querying per entity — at 8k
        # entities the per-entity version is thousands of round trips.
        from tawn.compiler.wiki import generate_entity_page, generate_links_index

        # No cap: a hardcoded limit(2000) silently wrote pages for 1,999 of
        # 17,612 entities, so most wikilinks pointed at files that were never
        # generated. Page writing is a cheap local file each; the graph views
        # do their own limiting.
        all_entities = session.query(Entity).all()
        by_id = {e.id: e for e in all_entities}
        related_map: dict[int, list[tuple[str, str]]] = {}
        backlink_map: dict[int, list[str]] = {}
        for ed in session.query(EntityEdge).all():
            src, dst = by_id.get(ed.from_entity_id), by_id.get(ed.to_entity_id)
            if src is None or dst is None:
                continue
            related_map.setdefault(src.id, []).append((dst.canonical, ed.relation))
            backlink_map.setdefault(dst.id, []).append(src.canonical)

        for ent in all_entities:
            generate_entity_page(
                ent,
                related=related_map.get(ent.id, [])[:50],
                backlinks=backlink_map.get(ent.id, [])[:50],
                staging_dir=staging_dir,
            )
        generate_links_index(session, staging_dir)

        atomic_swap(staging_dir, wiki_dir)

        # Phase 9 — State update
        for path in files_to_process:
            if path.exists():
                update_file_state(path, session)

        sentinel = home / _SENTINEL
        if sentinel.exists():
            sentinel.unlink()

        log_row.finished_at = datetime.datetime.utcnow()
        log_row.files_processed = files_processed
        log_row.chunks_added = chunks_added
        log_row.chunks_removed = chunks_removed
        log_row.entities_resolved = entities_resolved
        log_row.ok = True
        session.commit()

        return CompileResult(
            ok=True,
            files_processed=files_processed,
            chunks_added=chunks_added,
            chunks_removed=chunks_removed,
            entities_resolved=entities_resolved,
        )

    except Exception as exc:
        session.rollback()
        log_row.finished_at = datetime.datetime.utcnow()
        log_row.ok = False
        log_row.error = str(exc)
        session.add(log_row)
        session.commit()
        return CompileResult(ok=False, error=str(exc))


# Backwards-compat alias
compile = run_compile
