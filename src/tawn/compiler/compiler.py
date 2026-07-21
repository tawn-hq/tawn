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

from tawn.compiler.conflicts import resolve_conflicts
from tawn.compiler.delta import scan_raw, update_file_state
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
        # Phase 1 — Delta detection
        if rebuild:
            session.query(Chunk).delete()
            session.query(FileState).delete()
            session.flush()
            delta_files_new = list(raw_dir.rglob("*.md")) if raw_dir.exists() else []
            delta_files_changed: list[Path] = []
            delta_files_deleted: list[Path] = []
        else:
            from tawn.compiler.delta import DeltaResult
            delta = scan_raw(raw_dir, session)
            delta_files_new = delta.new
            delta_files_changed = delta.changed
            delta_files_deleted = delta.deleted

        files_to_process = delta_files_new + delta_files_changed
        files_processed = len(files_to_process)

        # Phase 2 — Parse
        all_chunks: list[ParsedChunk] = []
        for path in files_to_process:
            try:
                all_chunks.extend(parse_file(path))
            except Exception:
                pass

        # Phase 3 — Conflict resolution
        resolved_chunks = resolve_conflicts(all_chunks, wiki_dir=wiki_dir)

        # Phase 4 — Entity resolution
        review_dir.mkdir(parents=True, exist_ok=True)
        entities_resolved = extract_and_resolve(resolved_chunks, session, review_dir)

        # Phase 5+6 — Embed + write chunks
        chunks_added = 0
        embed_available = True
        for parsed in resolved_chunks:
            embedding: list[float] | None = None
            if embed_available:
                try:
                    embedding = embed_text(parsed.content, home)
                except EmbedError:
                    embed_available = False

            existing = (
                session.query(Chunk)
                .filter_by(source_path=parsed.source_path, chunk_index=parsed.chunk_index)
                .first()
            )
            if existing:
                if existing.content_hash != parsed.content_hash:
                    existing.content = parsed.content
                    existing.content_hash = parsed.content_hash
                    existing.priority_tier = parsed.priority_tier
                    existing.asof = parsed.asof
                    existing.ttl_days = parsed.ttl_days
                    existing.stale = False
                    existing.compiled_at = datetime.datetime.utcnow()
                    if embedding is not None:
                        existing.embedding = _storable_embedding(embedding)
            else:
                session.add(Chunk(
                    domain=parsed.frontmatter.get("domain"),
                    source_path=parsed.source_path,
                    chunk_index=parsed.chunk_index,
                    content=parsed.content,
                    embedding=_storable_embedding(embedding),
                    content_hash=parsed.content_hash,
                    priority_tier=parsed.priority_tier,
                    asof=parsed.asof,
                    ttl_days=parsed.ttl_days,
                    stale=False,
                    compiled_at=datetime.datetime.utcnow(),
                ))
                chunks_added += 1

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
