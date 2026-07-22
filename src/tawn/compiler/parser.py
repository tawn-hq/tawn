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

# Patterns that indicate garbage/noise content not worth indexing
_NOISE_PATTERNS = re.compile(
    r"\[SYSTEM NOTIFICATION\]|<task-notification>|<output-file>|"
    r"<system-reminder>|<command-name>|AUTOMATED.*NOT USER INPUT",
    re.IGNORECASE,
)
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _is_garbage(text: str) -> bool:
    """True if content is mostly noise (system tags, UUID lists, etc.)."""
    if _NOISE_PATTERNS.search(text):
        return True
    # Check if UUIDs dominate the content (raw JSON artifact lines)
    uuid_chars = sum(len(m.group()) for m in _UUID_RE.finditer(text))
    if uuid_chars > len(text) * 0.3:
        return True
    return False

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


def parse_history_session(path: Path) -> list[ParsedChunk]:
    """Convert a JSONL chat session into ParsedChunks.

    Each session becomes one or more chunks of alternating user/assistant turns,
    chunked at _MAX_CHARS boundaries. Domain left None (classifier runs later).
    """
    import json as _json

    lines = [_json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return []

    # derive title from first user message
    user_lines = [l for l in lines if l.get("role") == "user"]
    title = user_lines[0]["content"][:60].strip() if user_lines else path.stem

    # Format conversation as readable text for chunking
    turns: list[str] = []
    for entry in lines:
        role = entry.get("role", "")
        content = entry.get("content", "").strip()
        if role in ("user", "assistant") and content and not _is_garbage(content):
            turns.append(f"[{role}]: {content}")

    full_text = f"# Chat Session: {title}\n\n" + "\n\n".join(turns)

    asof = datetime.datetime.utcfromtimestamp(path.stat().st_mtime)

    raw_chunks = _split_by_size(full_text)
    result: list[ParsedChunk] = []
    for i, content in enumerate(raw_chunks):
        if not content.strip():
            continue
        result.append(ParsedChunk(
            source_path=str(path),
            chunk_index=i,
            content=content,
            frontmatter={"source_type": "history", "title": title},
            priority_tier=3,
            asof=asof,
        ))
    return result


def parse_text_file(path: Path, domain: str | None = None) -> list[ParsedChunk]:
    """Parse a plain text (.txt/.rst) file into chunks."""
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return []
    asof = datetime.datetime.utcfromtimestamp(path.stat().st_mtime)
    fm: dict = {}
    if domain:
        fm["domain"] = domain
    raw_chunks = _split_by_size(raw)
    result: list[ParsedChunk] = []
    for i, content in enumerate(raw_chunks):
        if not content.strip() or _is_garbage(content):
            continue
        result.append(ParsedChunk(
            source_path=str(path),
            chunk_index=i,
            content=content,
            frontmatter=fm,
            priority_tier=tier_for_path(path),
            asof=asof,
        ))
    return result


def parse_file(path: Path, domain: str | None = None) -> list[ParsedChunk]:
    """Parse a markdown file into a list of ParsedChunks."""
    if path.suffix.lower() == ".jsonl":
        return parse_history_session(path)
    if path.suffix.lower() in (".txt", ".rst"):
        return parse_text_file(path, domain)

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
        if _is_garbage(content):
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
