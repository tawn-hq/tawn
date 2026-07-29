"""Durable artifact storage — append-only, versioned, atomically written.

Everything Tawn generates that a user might want later lives here: diagrams,
research briefings, drafts. The storage rules exist because losing generated
work is unrecoverable in a way that losing a cache is not — the model that
produced it is nondeterministic, so a lost artifact cannot be regenerated, only
approximated.

The rules:

  1. **Append-only versions.** Revising an artifact writes `v002`; `v001` is
     never touched. There is no in-place edit and no overwrite path.
  2. **Atomic writes.** Content goes to a temp file in the same directory, is
     fsynced, then `os.replace`d into place. A crash mid-write leaves either
     the old file or the new one, never a truncated one.
  3. **Content before metadata.** The source file is durable before `meta.json`
     references it, so a crash leaves an unreferenced file (recoverable by
     `scan`) rather than a pointer to nothing.
  4. **A separate append-only log.** Every write also appends to
     `index.jsonl`. If `meta.json` is ever corrupted, the log still holds the
     full history.
  5. **Identical content does not create a version.** Re-rendering the same
     diagram returns the existing version instead of filling the directory.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ARTIFACTS_REL = "artifacts"
INDEX_NAME = "index.jsonl"
META_NAME = "meta.json"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "untitled"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class Version:
    number: int
    filename: str
    hash: str
    created_at: str
    note: str = ""


@dataclass
class Artifact:
    kind: str  # diagrams | briefings | drafts
    name: str
    slug: str
    fmt: str
    description: str = ""
    versions: list[Version] = field(default_factory=list)

    @property
    def latest(self) -> Version | None:
        return self.versions[-1] if self.versions else None


def artifacts_root(home: Path) -> Path:
    return Path(home) / ARTIFACTS_REL


def artifact_dir(home: Path, kind: str, slug: str) -> Path:
    return artifacts_root(home) / kind / slug


def _atomic_write(path: Path, text: str) -> None:
    """Write via a same-directory temp file, fsync, then rename.

    Same directory matters: `os.replace` is only atomic within a filesystem,
    and /tmp is frequently a different one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        # fsync the directory too, or the rename itself may not survive a crash.
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _append_index(home: Path, record: dict) -> None:
    path = artifacts_root(home) / INDEX_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _read_meta(home: Path, kind: str, slug: str) -> Artifact | None:
    meta = artifact_dir(home, kind, slug) / META_NAME
    if not meta.exists():
        return None
    try:
        raw = json.loads(meta.read_text())
    except Exception:
        return None
    return Artifact(
        kind=raw.get("kind", kind),
        name=raw.get("name", slug),
        slug=raw.get("slug", slug),
        fmt=raw.get("fmt", "txt"),
        description=raw.get("description", ""),
        versions=[Version(**v) for v in raw.get("versions", [])],
    )


def _write_meta(home: Path, art: Artifact) -> None:
    _atomic_write(
        artifact_dir(home, art.kind, art.slug) / META_NAME,
        json.dumps(
            {
                "kind": art.kind,
                "name": art.name,
                "slug": art.slug,
                "fmt": art.fmt,
                "description": art.description,
                "versions": [v.__dict__ for v in art.versions],
            },
            indent=2,
        ),
    )


def save_artifact(
    home: Path,
    kind: str,
    name: str,
    content: str,
    fmt: str,
    description: str = "",
    note: str = "",
) -> tuple[Artifact, Version, bool]:
    """Save a new version. Returns (artifact, version, is_new).

    Identical content returns the existing version rather than duplicating it.
    """
    home = Path(home)
    slug = slugify(name)
    art = _read_meta(home, kind, slug) or Artifact(
        kind=kind, name=name, slug=slug, fmt=fmt, description=description
    )
    if description:
        art.description = description

    digest = content_hash(content)
    existing = next((v for v in art.versions if v.hash == digest), None)
    if existing is not None:
        return art, existing, False

    number = (art.versions[-1].number + 1) if art.versions else 1
    filename = f"v{number:03d}.{fmt}"

    # Content first: a crash here leaves an unreferenced file that `scan`
    # recovers, rather than metadata pointing at a file that does not exist.
    _atomic_write(artifact_dir(home, kind, slug) / filename, content)

    version = Version(
        number=number,
        filename=filename,
        hash=digest,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        note=note,
    )
    art.versions.append(version)
    _write_meta(home, art)
    _append_index(
        home,
        {
            "ts": version.created_at, "kind": kind, "slug": slug, "name": name,
            "fmt": fmt, "version": number, "hash": digest, "note": note,
        },
    )
    return art, version, True


def read_artifact(
    home: Path, kind: str, name: str, version: int | None = None
) -> tuple[Artifact, Version, str] | None:
    home = Path(home)
    slug = slugify(name)
    art = _read_meta(home, kind, slug)
    if art is None or not art.versions:
        return None
    if version is None:
        v = art.versions[-1]
    else:
        v = next((x for x in art.versions if x.number == version), None)
        if v is None:
            return None
    path = artifact_dir(home, kind, slug) / v.filename
    if not path.exists():
        return None
    return art, v, path.read_text(errors="replace")


def list_artifacts(home: Path, kind: str | None = None) -> list[Artifact]:
    root = artifacts_root(Path(home))
    if not root.is_dir():
        return []
    kinds = [kind] if kind else [p.name for p in root.iterdir() if p.is_dir()]
    out: list[Artifact] = []
    for k in kinds:
        kdir = root / k
        if not kdir.is_dir():
            continue
        for d in sorted(kdir.iterdir()):
            if d.is_dir():
                art = _read_meta(Path(home), k, d.name)
                if art is not None:
                    out.append(art)
    return out


def scan(home: Path, kind: str, name: str) -> list[str]:
    """Version files present on disk, whatever the metadata says.

    The recovery path for rule 3: a file written just before a crash exists
    here even though `meta.json` never came to reference it.
    """
    d = artifact_dir(Path(home), kind, slugify(name))
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_file() and p.name != META_NAME)


def history(home: Path) -> list[dict]:
    """Every write ever recorded, from the append-only log."""
    path = artifacts_root(Path(home)) / INDEX_NAME
    if not path.exists():
        return []
    out = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out
