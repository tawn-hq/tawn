"""Document parsing — any format, cheapest route, behind a safety harness.

Dispatch is by content sniffing first and extension second, because a file's
name is a claim and its bytes are evidence: a `.txt` that is really a ZIP, or
an extensionless download, both parse correctly here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tawn.parsing import extractors as ex
from tawn.parsing.harness import (
    DEFAULT_LIMITS, Limits, ParseError, UnsafeDocument, cap_text, check_file,
    timeout,
)

__all__ = [
    "ParsedDocument", "ParseError", "UnsafeDocument", "Limits",
    "parse_file", "detect_format", "supported_formats",
]


def _ocr_image(path, limits):
    from tawn.parsing.ocr import extract_image

    return extract_image(path, limits)

#: format → (extractor, tier, human name). Tier is cost: 0 stdlib, 1 optional
#: library, 2 model.
FORMATS: dict[str, tuple] = {
    "text": (ex.extract_text, 0, "plain text"),
    "markdown": (ex.extract_text, 0, "Markdown"),
    "csv": (ex.extract_csv, 0, "CSV"),
    "json": (ex.extract_json, 0, "JSON"),
    "html": (ex.extract_html, 0, "HTML"),
    "xml": (ex.extract_text, 0, "XML"),
    "docx": (ex.extract_docx, 0, "Word"),
    "xlsx": (ex.extract_xlsx, 0, "Excel"),
    "pptx": (ex.extract_pptx, 0, "PowerPoint"),
    "odt": (ex.extract_odt, 0, "OpenDocument"),
    "epub": (ex.extract_epub, 0, "EPUB"),
    "pdf": (ex.extract_pdf, 1, "PDF"),
    "rtf": (ex.extract_rtf, 1, "RTF"),
    "doc": (ex.extract_doc, 1, "legacy Word"),
    "image": (_ocr_image, 2, "image (OCR)"),
}

_BY_EXTENSION = {
    ".txt": "text", ".log": "text", ".rst": "text", ".tex": "text",
    ".py": "text", ".js": "text", ".ts": "text", ".go": "text",
    ".rs": "text", ".java": "text", ".c": "text", ".h": "text",
    ".cpp": "text", ".sh": "text", ".sql": "text", ".yaml": "text",
    ".yml": "text", ".toml": "text", ".ini": "text", ".cfg": "text",
    ".md": "markdown", ".markdown": "markdown",
    ".csv": "csv", ".tsv": "csv",
    ".json": "json", ".jsonl": "json",
    ".html": "html", ".htm": "html",
    ".xml": "xml",
    ".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx",
    ".odt": "odt", ".ods": "odt", ".odp": "odt",
    ".epub": "epub", ".pdf": "pdf", ".rtf": "rtf", ".doc": "doc",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".tif": "image",
    ".tiff": "image", ".bmp": "image", ".gif": "image", ".webp": "image",
}

#: Magic bytes. Checked before the extension, since bytes cannot lie.
_MAGIC: list[tuple[bytes, str]] = [
    (b"%PDF-", "pdf"),
    (b"{\\rtf", "rtf"),
    (b"\xd0\xcf\x11\xe0", "doc"),  # OLE compound file
    (b"\x89PNG\r\n", "image"),
    (b"\xff\xd8\xff", "image"),        # JPEG
    (b"GIF87a", "image"),
    (b"GIF89a", "image"),
    (b"BM", "image"),
]

#: Inside a ZIP, these entries identify the specific Office/ODF format.
_ZIP_MARKERS = [
    ("word/document.xml", "docx"),
    ("xl/workbook.xml", "xlsx"),
    ("ppt/presentation.xml", "pptx"),
    ("mimetype", None),  # ODF and EPUB — resolved by reading it
]


@dataclass
class ParsedDocument:
    path: Path
    format: str
    text: str
    tier: int = 0
    chars: int = 0
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.text.strip())


def detect_format(path: Path) -> str:
    """Identify a document by its bytes, falling back to its extension.

    Sniffing first matters: downloads arrive extensionless, and an extension
    is a claim rather than evidence.
    """
    p = Path(path)
    try:
        with p.open("rb") as fh:
            head = fh.read(512)
    except OSError:
        head = b""

    for magic, fmt in _MAGIC:
        if head.startswith(magic):
            return fmt

    if head.startswith(b"PK\x03\x04"):
        fmt = _zip_format(p)
        if fmt:
            return fmt

    ext = p.suffix.lower()
    if ext in _BY_EXTENSION:
        return _BY_EXTENSION[ext]

    stripped = head.lstrip()[:64].lower()
    if stripped.startswith((b"<!doctype html", b"<html")):
        return "html"
    if stripped.startswith(b"<?xml"):
        return "xml"
    if stripped.startswith((b"{", b"[")):
        return "json"
    return "text"


def _zip_format(path: Path) -> str | None:
    import zipfile

    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            for marker, fmt in _ZIP_MARKERS:
                if marker not in names:
                    continue
                if fmt:
                    return fmt
                mimetype = zf.read("mimetype").decode("ascii", errors="replace")
                if "epub" in mimetype:
                    return "epub"
                if "opendocument" in mimetype:
                    return "odt"
            if any(n.lower().endswith((".xhtml", ".html")) for n in names):
                return "epub"
    except Exception:
        return None
    return None


def supported_formats() -> list[dict]:
    """What can be parsed, and what each costs."""
    cost = {
        0: "free (stdlib)",
        1: "free (needs a library)",
        2: "free (local OCR)",
        3: "paid (cloud model)",
    }
    return [
        {"format": name, "label": label, "tier": tier, "cost": cost[tier]}
        for name, (_, tier, label) in sorted(FORMATS.items())
    ]


def parse_file(
    path: Path,
    limits: Limits = DEFAULT_LIMITS,
    fmt: str | None = None,
    use_ocr: bool = True,
    allow_model: bool = False,
) -> ParsedDocument:
    """Extract text from a document of any supported format.

    The cost ladder runs cheapest-first and escalates only on an empty result:

        tier 0  stdlib          free
        tier 1  a library       free, needs installing
        tier 2  local OCR       free, needs tesseract      (`use_ocr`)
        tier 3  a cloud model   costs money, leaves the machine (`allow_model`)

    OCR is on by default because it is local and free; the model tier is off
    because it is neither. Raises `UnsafeDocument` when a safety limit trips
    and `ParseError` when the format is unreadable — never returns a partial
    result pretending to be a whole one.
    """
    p = Path(path)
    check_file(p, limits)

    fmt = fmt or detect_format(p)
    entry = FORMATS.get(fmt)
    if entry is None:
        raise ParseError(f"unsupported format: {fmt}")
    extractor, tier, label = entry

    warnings: list[str] = []
    with timeout(limits.timeout_seconds):
        text = extractor(p, limits)

    text = (text or "").strip()

    # Escalate one tier when the cheap route came back empty. A PDF with no
    # text layer is a scan, and OCR is the correct next step — local, free,
    # and nothing leaves the machine, which is why it precedes the model tier.
    if not text and fmt == "pdf" and use_ocr:
        from tawn.parsing.ocr import ocr_pdf

        try:
            with timeout(limits.timeout_seconds * 5):
                text = (ocr_pdf(p, limits) or "").strip()
            if text:
                tier = 2
                warnings.append("no text layer — read by OCR")
        except ParseError as exc:
            warnings.append(str(exc))

    capped = cap_text(text, limits)
    truncated = capped != text

    if not text:
        if fmt == "pdf" and not use_ocr:
            warnings.append(
                "no extractable text — this PDF is scanned. Retry with "
                "use_ocr=True, or install OCR: pip install 'tawn[ocr]'"
            )
        elif not warnings:
            warnings.append("no text could be extracted")
        if allow_model:
            from tawn.parsing.ocr import model_read

            try:
                text = model_read(p, limits)
                capped = cap_text(text, limits)
                tier = 3
            except ParseError as exc:
                warnings.append(str(exc))

    return ParsedDocument(
        path=p,
        format=fmt,
        text=capped,
        tier=tier,
        chars=len(capped),
        truncated=truncated,
        warnings=warnings,
    )
