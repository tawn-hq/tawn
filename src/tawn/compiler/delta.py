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


def scan_raw(raw_dir: Path, session: Session) -> DeltaResult:
    """Scan raw_dir for new/changed/deleted .md files vs file_state table."""
    result = DeltaResult()

    disk_files: dict[str, Path] = {
        str(f): f
        for f in raw_dir.rglob("*.md")
        if f.is_file()
    }

    known: dict[str, FileState] = {
        row.path: row
        for row in session.query(FileState).all()
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
