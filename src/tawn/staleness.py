"""Detect a long-running Tawn process older than the code on disk.

Nothing used to tell you this, and it caused three separate wrong conclusions
in one session:

  * a compile daemon started hours earlier kept re-ingesting files the
    on-disk code had learned to exclude, silently undoing CLI work;
  * a `pipx` install served an older release than the editable checkout being
    edited, so fixes appeared not to apply;
  * the web server answered API requests with pre-fix behaviour long after the
    fix landed, which read as the fix being wrong.

Each looked like a code bug and was really a stale process. A fingerprint
written at startup and compared later turns that into a plain warning.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_IGNORE_DIRS = {"__pycache__", ".pytest_cache", "dist"}


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def code_fingerprint(root: Path | None = None) -> str:
    """A short digest of the package's Python sources.

    Content-based rather than mtime-based: reinstalling or touching files
    without changing them should not read as a new version, and an editable
    checkout whose files are rewritten identically is not stale.
    """
    root = Path(root) if root is not None else _package_root()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if _IGNORE_DIRS.intersection(path.parts):
            continue
        try:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()[:16]


def _fingerprint_path(home: Path, name: str) -> Path:
    return Path(home) / f"{name}.fingerprint"


def write_running_fingerprint(home: Path, name: str, fingerprint: str | None = None) -> Path:
    """Record which code a process started with. Called at process start."""
    path = _fingerprint_path(home, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fingerprint or code_fingerprint())
    return path


def read_running_fingerprint(home: Path, name: str) -> str | None:
    path = _fingerprint_path(home, name)
    if not path.exists():
        return None
    value = path.read_text().strip()
    return value or None


def clear_running_fingerprint(home: Path, name: str) -> None:
    """Remove the record when a process stops, so a dead one is not judged."""
    _fingerprint_path(home, name).unlink(missing_ok=True)


def staleness_report(home: Path, name: str, current: str | None = None) -> dict:
    """Compare a running process's code against what is on disk now.

    A missing record means the process predates this check, which is not the
    same as being stale — say so rather than guessing.
    """
    running = read_running_fingerprint(home, name)
    current = current or code_fingerprint()
    stale = bool(running) and running != current
    return {
        "process": name,
        "running": running,
        "current": current,
        "stale": stale,
        "advice": (
            f"`tawn {name} stop && tawn {name} start` — the running {name} process "
            f"is using older code than what is on disk, so recent changes are not "
            f"taking effect. Restart it."
        ) if stale else "",
    }
