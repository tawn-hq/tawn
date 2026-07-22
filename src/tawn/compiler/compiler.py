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
from tawn.compiler.embedder import EmbedError, embed_text
from tawn.compiler.entities import extract_and_resolve
from tawn.compiler.parser import ParsedChunk, parse_file
from tawn.compiler.wiki import atomic_swap, generate_domain_index
from tawn.memory.schema import Chunk, CompileLog, Entity, FileState

_SENTINEL = ".compile-requested"


def _storable_embedding(vec: list[float] | None) -> list[float] | None:
    """Return None on SQLite (Text column can't store vectors)."""
    if vec is None:
        return None
    if "postgresql" not in os.environ.get("TAWN_DB_URL", ""):
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
        }
        if purge_paths:
            session.query(Chunk).filter(Chunk.source_path.in_(purge_paths)).delete(synchronize_session=False)
            session.query(FileState).filter(FileState.path.in_(purge_paths)).delete(synchronize_session=False)
            session.flush()

        # Phase 1 — Delta detection (raw/ + granted paths + history)
        if rebuild:
            session.query(Chunk).delete()
            session.query(FileState).delete()
            session.flush()
            _text_exts = {".md", ".txt", ".rst"}
            delta_files_new = (
                [f for f in raw_dir.rglob("*") if f.is_file() and f.suffix.lower() in _text_exts]
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
            _claude_projects = Path.home() / ".claude" / "projects"
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
            granted_delta = scan_granted(granted_read, session)
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
        for path in files_to_process:
            try:
                path_str = str(path)
                # classify domain for files outside raw/ (i.e. granted paths + history)
                inferred_domain: str | None = None
                if not path_str.startswith(raw_str) and not path_str.startswith(hist_str):
                    try:
                        content_preview = path.read_text(encoding="utf-8", errors="replace")[:2000]
                        inferred_domain = classify(path, content_preview)
                    except Exception:
                        pass
                chunks = parse_file(path, domain=inferred_domain)
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
        agent_mem_prefix = str(Path.home() / ".claude" / "projects")
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
        now = datetime.datetime.utcnow()
        _BATCH = 200
        for i, parsed in enumerate(resolved_chunks):
            embedding: list[float] | None = None
            if embed_available:
                try:
                    embedding = embed_text(parsed.content, home)
                except EmbedError:
                    embed_available = False

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
                    if embedding is not None:
                        existing.embedding = _storable_embedding(embedding)
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
                ))
                chunks_added += 1

            # Flush in batches to release memory pressure without a full commit
            if (i + 1) % _BATCH == 0:
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
        changed_domains: set[str] = set()
        for parsed in resolved_chunks:
            dom = parsed.frontmatter.get("domain")
            if dom:
                changed_domains.add(dom)

        for domain in changed_domains:
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
