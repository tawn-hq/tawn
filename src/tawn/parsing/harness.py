"""Safety harness for parsing untrusted documents.

Every file Tawn parses is untrusted — it came from a download, an email, a
shared drive. Document formats are a well-known attack surface: zip bombs,
XXE, billion-laughs, symlink escapes, files that decompress to hundreds of
gigabytes. The parsers are deliberately dumb about this; the harness is where
all of it is handled once.

Limits are conservative by default and raise rather than truncate silently,
because a caller that gets half a document and does not know it is worse off
than one that gets an error.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

#: A single file this large is refused outright.
MAX_FILE_BYTES = 200 * 1024 * 1024
#: Total bytes any archive may expand to.
MAX_EXPANDED_BYTES = 500 * 1024 * 1024
#: Compression ratio above which an archive is treated as a bomb.
MAX_COMPRESSION_RATIO = 200
#: Entries an archive may contain.
MAX_ARCHIVE_ENTRIES = 5_000
#: Extracted text is capped so one document cannot exhaust memory.
MAX_TEXT_CHARS = 5_000_000
#: Wall-clock seconds any single parse may take.
PARSE_TIMEOUT = 60


class ParseError(Exception):
    """Parsing failed for a reason the caller should see."""


class UnsafeDocument(ParseError):
    """The document tripped a safety limit. Refused, not truncated."""


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = MAX_FILE_BYTES
    max_expanded_bytes: int = MAX_EXPANDED_BYTES
    max_compression_ratio: int = MAX_COMPRESSION_RATIO
    max_archive_entries: int = MAX_ARCHIVE_ENTRIES
    max_text_chars: int = MAX_TEXT_CHARS
    timeout_seconds: int = PARSE_TIMEOUT


DEFAULT_LIMITS = Limits()


def check_file(path: Path, limits: Limits = DEFAULT_LIMITS) -> None:
    """Refuse a file before opening it."""
    p = Path(path)
    if not p.exists():
        raise ParseError(f"no such file: {p}")
    if p.is_symlink():
        # A symlink in a granted directory can point anywhere. Resolution is
        # the caller's job (through the grant check), not the parser's.
        raise UnsafeDocument(f"refusing to follow a symlink: {p}")
    if not p.is_file():
        raise ParseError(f"not a regular file: {p}")
    size = p.stat().st_size
    if size == 0:
        raise ParseError(f"empty file: {p}")
    if size > limits.max_file_bytes:
        raise UnsafeDocument(
            f"{p.name} is {size // (1024 * 1024)}MB, over the "
            f"{limits.max_file_bytes // (1024 * 1024)}MB limit"
        )


def safe_zip(path: Path, limits: Limits = DEFAULT_LIMITS) -> zipfile.ZipFile:
    """Open a ZIP after checking it is not a bomb and escapes nowhere.

    docx, xlsx, pptx, epub and odt are all ZIP containers, so this one check
    covers most of the "complex" formats.
    """
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ParseError(f"not a valid archive: {exc}") from exc

    infos = zf.infolist()
    if len(infos) > limits.max_archive_entries:
        zf.close()
        raise UnsafeDocument(
            f"archive has {len(infos)} entries, over the "
            f"{limits.max_archive_entries} limit"
        )

    total_expanded = 0
    for info in infos:
        name = info.filename
        # Absolute paths and traversal never belong in a document container.
        if name.startswith(("/", "\\")) or ".." in Path(name).parts:
            zf.close()
            raise UnsafeDocument(f"archive entry escapes its root: {name}")
        total_expanded += info.file_size
        if total_expanded > limits.max_expanded_bytes:
            zf.close()
            raise UnsafeDocument(
                f"archive expands past the "
                f"{limits.max_expanded_bytes // (1024 * 1024)}MB limit"
            )
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > limits.max_compression_ratio and info.file_size > 1024 * 1024:
                zf.close()
                raise UnsafeDocument(
                    f"{name} expands {int(ratio)}x — refusing as a possible zip bomb"
                )
    return zf


#: Bytes scanned for a DTD. A declaration must precede the root element, so a
#: bounded prefix is enough and a huge document is not read twice.
_DTD_SCAN_BYTES = 64 * 1024

_ENTITY_DECL = re.compile(rb"<!ENTITY\b", re.IGNORECASE)
_DOCTYPE = re.compile(rb"<!DOCTYPE\b", re.IGNORECASE)


def safe_xml(data: bytes | str) -> ET.Element:
    """Parse XML, refusing anything that declares entities.

    No document format Tawn reads — docx, xlsx, pptx, odt, epub — has any
    legitimate reason to declare an entity. Both classic XML attacks come
    through that door: XXE (an external entity reading a local file) and
    billion-laughs (nested internal entities exhausting memory).

    The check is a byte scan before parsing rather than an expat handler.
    `ElementTree.XMLParser` exposes no stable handle on the underlying expat
    parser across Python versions, so a handler-based guard fails silently on
    the versions where the attribute is missing — which is the worst possible
    behaviour for a security control. A scan cannot silently not-apply.
    """
    if isinstance(data, str):
        data = data.encode("utf-8", errors="replace")

    head = data[:_DTD_SCAN_BYTES]
    if _DOCTYPE.search(head) and _ENTITY_DECL.search(head):
        raise UnsafeDocument(
            "document declares XML entities — refusing to parse (XXE / "
            "entity-expansion risk)"
        )

    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ParseError(f"malformed XML: {exc}") from exc


def cap_text(text: str, limits: Limits = DEFAULT_LIMITS) -> str:
    """Cap extracted text, marking the truncation so it is never silent."""
    if len(text) <= limits.max_text_chars:
        return text
    return (
        text[: limits.max_text_chars]
        + f"\n\n[truncated at {limits.max_text_chars} characters]"
    )


def decode(data: bytes) -> str:
    """Decode bytes to text, trying the encodings that actually occur.

    `chardet` is used when installed; otherwise a short ladder covers the
    realistic cases. UTF-8 with replacement is the floor, so this never raises
    — a document with a few mangled characters still beats no document.
    """
    try:
        import chardet

        guess = chardet.detect(data[:100_000])
        if guess and guess.get("encoding") and (guess.get("confidence") or 0) > 0.7:
            try:
                return data.decode(guess["encoding"], errors="replace")
            except (LookupError, UnicodeDecodeError):
                pass
    except ImportError:
        pass

    for encoding in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


class timeout:
    """Bound a parse in wall-clock time.

    SIGALRM only works on the main thread of a Unix process, so this degrades
    to a no-op elsewhere rather than pretending to protect. The size limits
    above are the real defence; this catches pathological-but-small inputs.
    """

    def __init__(self, seconds: int = PARSE_TIMEOUT):
        self.seconds = seconds
        self._previous = None
        self._armed = False

    def __enter__(self):
        import signal
        import threading

        if os.name != "posix" or threading.current_thread() is not threading.main_thread():
            return self
        try:
            self._previous = signal.signal(signal.SIGALRM, self._fire)
            signal.alarm(self.seconds)
            self._armed = True
        except (ValueError, AttributeError, OSError):
            self._armed = False
        return self

    def _fire(self, signum, frame):
        raise ParseError(f"parsing exceeded {self.seconds}s")

    def __exit__(self, *exc):
        if not self._armed:
            return False
        import signal

        signal.alarm(0)
        if self._previous is not None:
            signal.signal(signal.SIGALRM, self._previous)
        return False
