"""Tawn ignore rules — loaded from ~/.tawn/ignore, like .gitignore.

Supports:
  - Directory name segments  (node_modules/ — matches anywhere in path)
  - Glob patterns            (*.pyc — matched against filename)
  - Absolute / home paths    (/home/user/project/venv — skip that exact subtree)
  - Auto-detection           any dir containing pyvenv.cfg is treated as a venv

Lines starting with '#' are comments. Blank lines ignored.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

DEFAULT_IGNORE = """\
# ── Python ────────────────────────────────────────────────────────────────────
__pycache__/
*.pyc
*.pyo
*.pyd
.venv/
venv/
vevn/
env/
.env/
site-packages/
dist-packages/
dist-info/
egg-info/
*.egg-info/
*.egg
.tox/
.mypy_cache/
.ruff_cache/
.pytest_cache/
htmlcov/
coverage/
.coverage
coverage.xml

# ── JavaScript / Node ──────────────────────────────────────────────────────────
node_modules/
.npm/
.yarn/
.pnp/
.next/
.nuxt/
.output/
.parcel-cache/

# ── Build artifacts ───────────────────────────────────────────────────────────
dist/
build/
out/
*.o
*.so
*.dylib
*.a
*.lib
*.dll
*.exe

# ── Version control ───────────────────────────────────────────────────────────
.git/
.svn/
.hg/
.bzr/

# ── IDE / editor ──────────────────────────────────────────────────────────────
.idea/
.vscode/
*.suo
.vs/

# ── Mobile ────────────────────────────────────────────────────────────────────
Pods/
DerivedData/
*.xcworkspace/

# ── OS junk ───────────────────────────────────────────────────────────────────
.DS_Store
Thumbs.db
desktop.ini

# ── Test / coverage reports ───────────────────────────────────────────────────
.nyc_output/
lcov-report/

# ── Add absolute paths below to ignore specific CLI tool roots ─────────────────
# Example:  /home/you/projects/some-tool/node_modules
# Example:  ~/work/legacy-api/venv
"""


def _ignore_path(home: Path) -> Path:
    return home / "ignore"


def write_default_ignore(home: Path) -> Path:
    path = _ignore_path(home)
    if not path.exists():
        path.write_text(DEFAULT_IGNORE)
    return path


def _is_venv(p: Path) -> bool:
    """True if directory looks like a Python virtualenv regardless of name."""
    if not p.is_dir():
        return False
    return (p / "pyvenv.cfg").exists() or (p / "lib").is_dir() and any(
        (p / "lib").glob("python*/site-packages")
    )


def load_ignore_patterns(home: Path) -> tuple[frozenset[str], list[str], list[Path]]:
    """Load ignore patterns from ~/.tawn/ignore.

    Returns (dir_segments, glob_patterns, abs_paths):
      dir_segments  — exact dir names to skip anywhere in path
      glob_patterns — fnmatch patterns for filenames
      abs_paths     — absolute path prefixes to skip entirely
    """
    path = _ignore_path(home)
    if not path.exists():
        write_default_ignore(home)

    dir_segments: set[str] = set()
    glob_patterns: list[str] = []
    abs_paths: list[Path] = []

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("/") or line.startswith("~"):
            # Absolute or home-relative path
            abs_paths.append(Path(line).expanduser().resolve())
        elif line.endswith("/"):
            dir_segments.add(line.rstrip("/"))
        elif "*" in line or "?" in line or "[" in line:
            glob_patterns.append(line)
        else:
            dir_segments.add(line)

    return frozenset(dir_segments), glob_patterns, abs_paths


def should_ignore(
    path: Path,
    dir_segments: frozenset[str],
    glob_patterns: list[str],
    abs_paths: list[Path],
) -> bool:
    """Return True if path should be excluded from indexing."""
    parts = path.parts
    name = path.name

    # Absolute prefix match
    for ap in abs_paths:
        try:
            path.relative_to(ap)
            return True
        except ValueError:
            pass

    # Any segment matches an ignored dir name
    if dir_segments.intersection(parts):
        return True

    # Filename glob
    for pattern in glob_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True

    # Auto-detect venv by content (catches oddly-named envs like vevn/)
    for i, part in enumerate(parts):
        candidate = Path(*parts[:i + 1])
        if _is_venv(candidate):
            return True

    return False
