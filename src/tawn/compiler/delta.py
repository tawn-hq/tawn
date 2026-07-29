"""Delta detection — compare raw/ tree against file_state table."""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from tawn.memory.schema import FileState


@dataclass
class DeltaResult:
    new: list[Path] = field(default_factory=list)
    changed: list[Path] = field(default_factory=list)
    deleted: list[Path] = field(default_factory=list)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_TEXT_EXTS = {".md", ".txt", ".rst"}

# Fallback hardcoded set used before home is known (e.g. compiler bootstrap).
# The real patterns come from ~/.tawn/ignore via tawn.ignore.load_ignore_patterns().
_IGNORE_DIRS: frozenset[str] = frozenset({
    "node_modules", ".venv", "venv", "vevn", "env", ".env",
    "__pycache__", ".git", ".svn", ".hg", ".bzr",
    "site-packages", "dist-packages", "dist-info", "egg-info",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    ".cache", ".npm", ".yarn", ".pnp",
    "build", "dist", ".next", ".nuxt", ".output",
    "coverage", ".nyc_output", "htmlcov",
    "vendor", "Pods", "DerivedData",
    # Tawn's own working directory, not memory. The entity resolver writes
    # every ambiguous match here for a human to triage; indexing that output
    # fed the compiler its own discards — 14,545 chunks and most of the
    # entity noise on the first real corpus. Reviews get their own surface,
    # so this stays out of the memory store permanently.
    "review-queue",
})


def scan_raw(raw_dir: Path, session: Session) -> DeltaResult:
    """Scan raw_dir for new/changed/deleted text files vs file_state table."""
    result = DeltaResult()

    disk_files: dict[str, Path] = {
        str(f): f
        for f in raw_dir.rglob("*")
        if f.is_file()
        and f.suffix.lower() in _TEXT_EXTS
        and not _IGNORE_DIRS.intersection(f.parts)
    }

    # Scoped to raw_dir. This used to load *every* FileState row while
    # `disk_files` only globbed raw/, so granted repos, history and agent
    # memory all looked deleted on every compile — their chunks were removed
    # and re-added on alternating runs (one real pass added 1,347 chunks, the
    # next removed 2,303). `scan_raw` only has authority over raw/.
    raw_prefix = str(raw_dir)
    known: dict[str, FileState] = {
        row.path: row
        for row in session.query(FileState)
        .filter(FileState.path.like(raw_prefix + "%"))
        .all()
    }

    for path_str, path in disk_files.items():
        if path_str not in known:
            result.new.append(path)
        else:
            state = known[path_str]
            if path.stat().st_mtime != state.mtime:
                if _file_hash(path) != state.content_hash:
                    result.changed.append(path)

    for path_str in known:
        if path_str not in disk_files:
            result.deleted.append(Path(path_str))

    return result


def scan_granted(read_paths: list[Path], session: Session, home: Path | None = None) -> DeltaResult:
    """Scan user-granted read paths for new/changed text files."""
    from tawn.home import tawn_home as _tawn_home
    from tawn.ignore import load_ignore_patterns, should_ignore
    _home = home or _tawn_home()
    dir_segs, glob_pats, abs_paths = load_ignore_patterns(_home)

    result = DeltaResult()
    known: dict[str, FileState] = {
        row.path: row
        for row in session.query(FileState).all()
    }
    for root in read_paths:
        root = root.expanduser().resolve()
        if not root.exists():
            continue
        glob = root.rglob("*") if root.is_dir() else [root]
        for f in glob:
            if not f.is_file() or f.suffix.lower() not in _TEXT_EXTS:
                continue
            if should_ignore(f, dir_segs, glob_pats, abs_paths):
                continue
            path_str = str(f)
            if path_str not in known:
                result.new.append(f)
            else:
                state = known[path_str]
                if f.stat().st_mtime != state.mtime and _file_hash(f) != state.content_hash:
                    result.changed.append(f)
    return result


def scan_history(home: Path, session: Session) -> DeltaResult:
    """Scan ~/.tawn/history/ for new/changed session JSONL files."""
    result = DeltaResult()
    history_dir = home / "history"
    if not history_dir.exists():
        return result
    known: dict[str, FileState] = {
        row.path: row
        for row in session.query(FileState).all()
    }
    for f in history_dir.glob("*.jsonl"):
        if not f.is_file():
            continue
        path_str = str(f)
        if path_str not in known:
            result.new.append(f)
        else:
            state = known[path_str]
            if f.stat().st_mtime != state.mtime and _file_hash(f) != state.content_hash:
                result.changed.append(f)
    return result


def scan_agent_memory(session: Session) -> DeltaResult:
    """Scan Claude Code project memory dirs (~/.claude/projects/*/memory/).

    These .md files contain structured notes (preferences, roles, project context)
    written by Claude Code's auto-memory system. Valuable tawn input.
    """
    from tawn.home import agent_memory_root

    result = DeltaResult()
    projects_dir = agent_memory_root()
    if not projects_dir.exists():
        return result
    known: dict[str, FileState] = {
        row.path: row
        for row in session.query(FileState).all()
    }
    for memory_dir in projects_dir.glob("*/memory"):
        if not memory_dir.is_dir():
            continue
        for f in memory_dir.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in _TEXT_EXTS:
                continue
            # Skip index files that are just pointers to other memories
            if f.name in ("MEMORY.md",):
                continue
            path_str = str(f)
            if path_str not in known:
                result.new.append(f)
            else:
                state = known[path_str]
                if f.stat().st_mtime != state.mtime and _file_hash(f) != state.content_hash:
                    result.changed.append(f)
    return result


def update_file_state(path: Path, session: Session) -> None:
    """Upsert file_state for path after a successful compile."""
    path_str = str(path)
    content_hash = _file_hash(path)
    mtime = path.stat().st_mtime
    existing = session.get(FileState, path_str)
    if existing:
        existing.mtime = mtime
        existing.content_hash = content_hash
        existing.compiled_at = datetime.datetime.utcnow()
    else:
        session.add(FileState(
            path=path_str,
            mtime=mtime,
            content_hash=content_hash,
            compiled_at=datetime.datetime.utcnow(),
        ))
