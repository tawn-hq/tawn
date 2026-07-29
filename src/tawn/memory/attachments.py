"""Attachments — parsed once, on attach, then referenced by id.

The naive approach inlines a file's text into the chat message. That is wrong
three ways: a PDF read as text is binary noise, the content lands in the
conversation history and is therefore re-sent on *every* later turn, and a
large document silently pushes the request past what the provider will accept
— which shows up to the user as a chat that hangs with no reply.

So parsing happens when the file is attached, the extracted text is stored here
under an id, and a turn references the ids it needs. The text enters the model
context exactly once, for the turn it was attached to.
"""

from __future__ import annotations

import datetime
import json
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path

ATTACH_REL = "attachments"
#: Text kept per attachment. Beyond this a document is not "context" any more,
#: it is a corpus — and that is what `tawn compile` and recall are for.
MAX_TEXT_CHARS = 120_000
#: Bytes accepted on upload.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
#: Attachments older than this are swept. Long enough to finish a session,
#: short enough that ~/.tawn does not accumulate every file ever dragged in.
TTL_HOURS = 48


@dataclass
class Attachment:
    id: str
    name: str
    format: str
    chars: int
    text: str = ""
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    created_at: str = ""

    def meta(self) -> dict:
        """Everything except the text — what the UI needs."""
        return {
            "id": self.id,
            "name": self.name,
            "format": self.format,
            "chars": self.chars,
            "truncated": self.truncated,
            "warnings": self.warnings,
        }


def _root(home: Path) -> Path:
    return Path(home) / ATTACH_REL


def new_id() -> str:
    return secrets.token_hex(8)


def _path(home: Path, attach_id: str) -> Path:
    # ids are generated, but this is the one place a caller-supplied string
    # reaches the filesystem.
    safe = re.sub(r"[^a-f0-9]", "", attach_id)[:32]
    return _root(home) / f"{safe}.json"


def save(home: Path, attachment: Attachment) -> Attachment:
    root = _root(Path(home))
    root.mkdir(parents=True, exist_ok=True)
    if not attachment.created_at:
        attachment.created_at = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
    _path(Path(home), attachment.id).write_text(
        json.dumps(
            {
                "id": attachment.id,
                "name": attachment.name,
                "format": attachment.format,
                "chars": attachment.chars,
                "text": attachment.text,
                "truncated": attachment.truncated,
                "warnings": attachment.warnings,
                "created_at": attachment.created_at,
            }
        )
    )
    return attachment


def load(home: Path, attach_id: str) -> Attachment | None:
    p = _path(Path(home), attach_id)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text())
    except Exception:
        return None
    return Attachment(**raw)


def remove(home: Path, attach_id: str) -> bool:
    p = _path(Path(home), attach_id)
    if not p.is_file():
        return False
    p.unlink()
    return True


def ingest(home: Path, name: str, data: bytes) -> Attachment:
    """Parse an uploaded file and store its text.

    Runs through the same harness `tawn compile` uses, so a zip bomb or a
    malicious document is refused here rather than at read time.
    """
    import tempfile

    from tawn.parsing import ParseError, parse_file

    if len(data) > MAX_UPLOAD_BYTES:
        raise ParseError(
            f"{name} is {len(data) // (1024 * 1024)}MB, over the "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)}MB attachment limit"
        )
    if not data:
        raise ParseError(f"{name} is empty")

    suffix = Path(name).suffix
    tmp = Path(tempfile.mkdtemp(prefix="tawn-attach-")) / (
        Path(name).name or f"upload{suffix}"
    )
    try:
        tmp.write_bytes(data)
        doc = parse_file(tmp)
        text = doc.text
        truncated = doc.truncated
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + "\n\n[attachment truncated]"
            truncated = True
        return save(
            Path(home),
            Attachment(
                id=new_id(),
                name=name,
                format=doc.format,
                chars=len(text),
                text=text,
                truncated=truncated,
                warnings=list(doc.warnings),
            ),
        )
    finally:
        import shutil

        shutil.rmtree(tmp.parent, ignore_errors=True)


def context_block(home: Path, ids: list[str]) -> str:
    """The text for a turn's attachments, ready to prepend to the prompt."""
    parts: list[str] = []
    for attach_id in ids:
        att = load(Path(home), attach_id)
        if att is None or not att.text.strip():
            continue
        parts.append(f"--- attached: {att.name} ({att.format}) ---\n{att.text}")
    return "\n\n".join(parts)


def sweep(home: Path, ttl_hours: int = TTL_HOURS, now: datetime.datetime | None = None) -> int:
    """Delete attachments past their TTL. Returns how many went."""
    root = _root(Path(home))
    if not root.is_dir():
        return 0
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=ttl_hours)
    removed = 0
    for f in root.glob("*.json"):
        try:
            raw = json.loads(f.read_text())
            created = datetime.datetime.fromisoformat(raw.get("created_at", ""))
        except Exception:
            # Unreadable metadata means we cannot date it; leave it rather than
            # deleting something that might still be in use.
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=datetime.timezone.utc)
        if created < cutoff:
            f.unlink()
            removed += 1
    return removed
