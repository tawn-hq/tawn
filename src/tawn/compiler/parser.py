"""Markdown + frontmatter parser → list of ParsedChunk.

Splits on heading boundaries; max ~800 tokens (≈ 3200 chars) per chunk.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter  # python-frontmatter

_MAX_CHARS = 3200  # ≈ 800 tokens at 4 chars/token

_TIER_MAP = {
    "identity": 1,
    "vault": 2,
    "agent-notes": 3,
    "federation": 4,
}


@dataclass
class ParsedChunk:
    source_path: str
    chunk_index: int
    content: str
    frontmatter: dict = field(default_factory=dict)
    priority_tier: int = 3
    asof: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    ttl_days: int | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]


def tier_for_path(path: str | Path) -> int:
    parts = Path(path).parts
    # Check raw/<subdir> pattern
    raw_idx = next((i for i, p in enumerate(parts) if p == "raw"), None)
    if raw_idx is not None and raw_idx + 1 < len(parts):
        sub = parts[raw_idx + 1]
        for key, tier in _TIER_MAP.items():
            if sub.startswith(key):
                return tier
    # Check bare subdir (e.g. federation/ without raw/ parent)
    for part in parts:
        for key, tier in _TIER_MAP.items():
            if part.startswith(key):
                return tier
    return 3


def _split_sections(text: str) -> list[str]:
    """Split on markdown heading boundaries (h1–h3)."""
    parts = re.split(r"(?m)^(#{1,3} .+)$", text)
    sections: list[str] = []
    current = ""
    for part in parts:
        if re.match(r"^#{1,3} ", part):
            if current.strip():
                sections.append(current.strip())
            current = part + "\n"
        else:
            current += part
    if current.strip():
        sections.append(current.strip())
    return sections or [text.strip()]


def _split_by_size(text: str, max_chars: int = _MAX_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    while len(text) > max_chars:
        split_at = text.rfind("\n", 0, max_chars)
        if split_at == -1:
            split_at = max_chars
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks


def parse_file(path: Path) -> list[ParsedChunk]:
    """Parse a markdown file into a list of ParsedChunks."""
    raw = path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)
    fm: dict = dict(post.metadata)
    body: str = post.content.strip()

    tier = tier_for_path(path)

    asof_raw = fm.get("asof")
    if asof_raw:
        if isinstance(asof_raw, datetime.datetime):
            asof = asof_raw.replace(tzinfo=None)
        else:
            try:
                asof = datetime.datetime.fromisoformat(str(asof_raw).rstrip("Z"))
            except ValueError:
                asof = datetime.datetime.utcnow()
    else:
        asof = datetime.datetime.utcfromtimestamp(path.stat().st_mtime)

    ttl_days = fm.get("ttl_days")

    sections = _split_sections(body)
    raw_chunks: list[str] = []
    for section in sections:
        raw_chunks.extend(_split_by_size(section))

    result: list[ParsedChunk] = []
    for i, content in enumerate(raw_chunks):
        if not content.strip():
            continue
        result.append(ParsedChunk(
            source_path=str(path),
            chunk_index=i,
            content=content,
            frontmatter=fm,
            priority_tier=tier,
            asof=asof,
            ttl_days=int(ttl_days) if ttl_days is not None else None,
        ))
    return result
