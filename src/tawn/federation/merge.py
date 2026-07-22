"""Merge pending FederationRecords into raw/imports/ and queue compile."""

from __future__ import annotations

import datetime
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tawn.compiler.compiler import request_compile
from tawn.federation.adapters.base import BaseAdapter
from tawn.federation.dispatcher import ADAPTER_CHAIN, dispatch, fingerprint
from tawn.federation.normalizer import infer_domain, infer_project, normalise, write_to_raw_imports
from tawn.federation.schema import FederationRecord

_UTC = datetime.timezone.utc

# Fallback ignore set (used before home is resolved)
_IGNORE_DIRS: frozenset[str] = frozenset({
    "node_modules", ".venv", "venv", "vevn", "env", ".env",
    "__pycache__", ".git", ".svn", ".hg",
    "site-packages", "dist-packages", "dist-info", "egg-info",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    "build", "dist",
})


def ingest_file(
    home: Path,
    session: Session,
    path: Path,
    source: str,
) -> FederationRecord | None:
    """Create a pending FederationRecord for path. Returns None if duplicate."""
    fp = fingerprint(path)
    exists = session.query(FederationRecord).filter_by(
        source=source,
        source_path=str(path),
        fingerprint=fp,
    ).first()
    if exists:
        return None
    record = FederationRecord(
        source=source,
        source_path=str(path),
        fingerprint=fp,
        status="pending",
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    return record


def scan_all_sources(home: Path, session: Session) -> int:
    """Walk all registered federation sources and ingest files not yet in DB.

    Called at server startup to bootstrap existing history files that predate
    the watcher. Returns count of newly-created FederationRecord rows.
    """
    from tawn.federation.config import load_config
    from tawn.federation.dispatcher import dispatch

    sources = load_config(home)
    inbox = home / "federation" / "inbox"
    ingested = 0

    scan_dirs: list[Path] = [inbox] if inbox.exists() else []
    for src in sources:
        p = Path(src.path).expanduser()
        if p.exists():
            scan_dirs.append(p)

    from tawn.ignore import load_ignore_patterns, should_ignore
    dir_segs, glob_pats, abs_paths = load_ignore_patterns(home)

    for scan_dir in scan_dirs:
        for path in scan_dir.rglob("*"):
            if not path.is_file():
                continue
            # Skip ignored paths (venvs, caches, package trees, user-defined)
            if should_ignore(path, dir_segs, glob_pats, abs_paths):
                continue
            # Skip memory/ subdirectories inside Claude Code project dirs
            if "memory" in path.parts:
                continue
            adapter = dispatch(path)
            if adapter is None:
                continue
            record = ingest_file(home, session, path, source=adapter.name)
            if record is not None:
                ingested += 1

    return ingested


def merge_pending(home: Path, session: Session) -> dict:
    """Process all pending FederationRecord rows. Returns counts dict."""
    records = session.query(FederationRecord).filter_by(status="pending").all()
    merged = failed = skipped = 0

    # Build adapter lookup by name
    adapter_map: dict[str, BaseAdapter] = {a.name: a for a in ADAPTER_CHAIN}

    for record in records:
        path = Path(record.source_path)
        try:
            if not path.exists():
                raise FileNotFoundError(f"source file missing: {path}")
            adapter = dispatch(path)
            if adapter is None:
                record.status = "skipped"
                session.commit()
                skipped += 1
                continue
            turns = adapter.parse(path)
            if not turns:
                record.status = "skipped"
                session.commit()
                skipped += 1
                continue
            domain = infer_domain(turns, adapter, source_path=path)
            project = infer_project(path, adapter.name)
            content = normalise(turns, source=record.source, domain=domain, project=project)
            write_to_raw_imports(home, record.source, content, project=project)
            record.domain = domain
            record.project = project
            record.status = "merged"
            record.merged_at = datetime.datetime.now(_UTC)
            session.commit()
            merged += 1
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)[:500]
            session.commit()
            failed += 1

    if merged > 0:
        request_compile(home)

    return {"merged": merged, "failed": failed, "skipped": skipped}
