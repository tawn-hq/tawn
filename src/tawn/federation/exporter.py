"""Export compiled Tawn memory to JSONL and/or markdown bundle."""

from __future__ import annotations

import datetime
import json
import stat
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from tawn.memory.schema import Chunk, Entity


def export(home: Path, session: Session, fmt: str = "both") -> dict:
    """Write export bundle to federation/exports/YYYY-MM-DD/.

    fmt: "jsonl" | "markdown" | "both"
    Returns {"ok": True, "format": str, "out": str, "files": list[str]}.
    """
    today = datetime.date.today().strftime("%Y-%m-%d")
    out_dir = home / "federation" / "exports" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = session.query(Chunk).all()
    entities = session.query(Entity).all()

    if not chunks and not entities:
        return {"ok": True, "format": fmt, "out": str(out_dir), "files": []}

    files: list[str] = []

    if fmt in ("jsonl", "both"):
        p = _export_jsonl(chunks, entities, out_dir)
        if p:
            files.append(str(p))

    if fmt in ("markdown", "both"):
        ps = _export_markdown(chunks, entities, out_dir)
        files.extend(str(p) for p in ps)

    return {"ok": True, "format": fmt, "out": str(out_dir), "files": files}


def _export_jsonl(
    chunks: list[Chunk], entities: list[Entity], out_dir: Path
) -> Path | None:
    if not chunks:
        return None
    entity_by_domain: dict[str, list[str]] = defaultdict(list)
    for e in entities:
        if e.domain:
            entity_by_domain[e.domain].append(e.canonical)

    path = out_dir / "export.jsonl"
    with path.open("w") as f:
        for c in chunks:
            row = {
                "id": c.id,
                "domain": c.domain,
                "content": c.content,
                "source": c.source_path,
                "entities": entity_by_domain.get(c.domain or "", []),
                "compiled_at": c.compiled_at.isoformat() if c.compiled_at else None,
                "stale": c.stale,
            }
            f.write(json.dumps(row) + "\n")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return path


def _export_markdown(
    chunks: list[Chunk], entities: list[Entity], out_dir: Path
) -> list[Path]:
    by_domain: dict[str, list[Chunk]] = defaultdict(list)
    for c in chunks:
        by_domain[c.domain or "unknown"].append(c)

    entity_by_domain: dict[str, list[str]] = defaultdict(list)
    for e in entities:
        if e.domain:
            entity_by_domain[e.domain].append(e.canonical)

    paths: list[Path] = []
    for domain, domain_chunks in by_domain.items():
        lines = [f"# {domain.title()} — Tawn Export\n"]
        ents = entity_by_domain.get(domain, [])
        if ents:
            lines.append("## Key Entities\n")
            for ent in ents[:20]:
                lines.append(f"- {ent}")
            lines.append("")
        lines.append("## Knowledge\n")
        for c in domain_chunks:
            lines.append(f"### {c.source_path}\n")
            lines.append(c.content[:500])
            lines.append("")
        p = out_dir / f"{domain}.md"
        p.write_text("\n".join(lines))
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)
        paths.append(p)

    index_lines = ["# Tawn Export Index\n", f"Generated: {datetime.date.today()}\n",
                   "## Domains\n"]
    for domain in sorted(by_domain):
        index_lines.append(f"- [{domain}]({domain}.md)")
    idx = out_dir / "index.md"
    idx.write_text("\n".join(index_lines))
    idx.chmod(stat.S_IRUSR | stat.S_IWUSR)
    paths.append(idx)
    return paths
