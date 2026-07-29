"""Format-specific text extraction, cheapest tier first.

Cost here means real cost: CPU, dependencies, and money. The ladder is

  tier 0  stdlib only          free — plain text, CSV, JSON, HTML, and every
                               ZIP+XML format (docx, xlsx, pptx, odt, epub)
  tier 1  an optional library  free, but needs installing (PDF, legacy .doc)
  tier 2  a model              costs money — OCR and scanned pages only

Most "hard" formats are tier 0: Office and OpenDocument files are ZIP
containers full of XML, which `zipfile` and `ElementTree` read without any
third-party package. Reaching for a library first would have made the common
case needlessly expensive.

Every extractor returns plain text and raises `ParseError` with an actionable
message — including which package to install — rather than failing silently.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from tawn.parsing.harness import (
    Limits, ParseError, decode, safe_xml, safe_zip,
)

#: XML namespaces used by the Office and OpenDocument formats.
_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "sl": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}


# ── tier 0: plain formats ────────────────────────────────────────────────────

def extract_text(path: Path, limits: Limits) -> str:
    return decode(Path(path).read_bytes())


def extract_csv(path: Path, limits: Limits) -> str:
    """Rows as pipe-delimited lines — readable by a model, unlike raw CSV."""
    raw = decode(Path(path).read_bytes())
    try:
        dialect = csv.Sniffer().sniff(raw[:4096])
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(raw), dialect))
    return "\n".join(" | ".join(cell.strip() for cell in row) for row in rows if row)


def extract_json(path: Path, limits: Limits) -> str:
    raw = decode(Path(path).read_bytes())
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        # JSONL, or malformed. The text is still worth returning.
        return raw


def extract_html(path: Path, limits: Limits) -> str:
    raw = decode(Path(path).read_bytes())
    return html_to_text(raw)


def html_to_text(raw: str) -> str:
    """Strip markup. Uses BeautifulSoup when installed, regex otherwise."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()
    except ImportError:
        pass
    text = re.sub(r"(?is)<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = _unescape_entities(text)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", text)).strip()


def _unescape_entities(text: str) -> str:
    import html as html_mod

    return html_mod.unescape(text)


# ── tier 0: ZIP + XML formats ────────────────────────────────────────────────

def extract_docx(path: Path, limits: Limits) -> str:
    """Word. A ZIP whose `document.xml` holds the paragraphs."""
    with safe_zip(path, limits) as zf:
        try:
            xml = zf.read("word/document.xml")
        except KeyError as exc:
            raise ParseError("not a Word document: no word/document.xml") from exc
    root = safe_xml(xml)
    paragraphs = []
    for para in root.iter(f"{{{_NS['w']}}}p"):
        runs = [t.text or "" for t in para.iter(f"{{{_NS['w']}}}t")]
        line = "".join(runs).strip()
        if line:
            paragraphs.append(line)
    return "\n\n".join(paragraphs)


def extract_xlsx(path: Path, limits: Limits) -> str:
    """Excel. Shared strings plus each sheet's cells."""
    with safe_zip(path, limits) as zf:
        names = set(zf.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = safe_xml(zf.read("xl/sharedStrings.xml"))
            for si in root:
                shared.append("".join(t.text or "" for t in si.iter() if t.text))

        sheets = sorted(n for n in names if n.startswith("xl/worksheets/sheet"))
        if not sheets:
            raise ParseError("not a spreadsheet: no worksheets found")

        out: list[str] = []
        for sheet in sheets:
            root = safe_xml(zf.read(sheet))
            out.append(f"--- {Path(sheet).stem} ---")
            for row in root.iter(f"{{{_NS['sl']}}}row"):
                cells = []
                for c in row.iter(f"{{{_NS['sl']}}}c"):
                    v = c.find(f"{{{_NS['sl']}}}v")
                    if v is None or v.text is None:
                        continue
                    if c.get("t") == "s":  # index into shared strings
                        try:
                            cells.append(shared[int(v.text)])
                        except (ValueError, IndexError):
                            cells.append(v.text)
                    else:
                        cells.append(v.text)
                if cells:
                    out.append(" | ".join(cells))
        return "\n".join(out)


def extract_pptx(path: Path, limits: Limits) -> str:
    """PowerPoint. One section per slide."""
    with safe_zip(path, limits) as zf:
        slides = sorted(
            n for n in zf.namelist()
            if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )
        if not slides:
            raise ParseError("not a presentation: no slides found")
        out: list[str] = []
        for i, slide in enumerate(slides, 1):
            root = safe_xml(zf.read(slide))
            lines = [
                t.text.strip()
                for t in root.iter(f"{{{_NS['a']}}}t")
                if t.text and t.text.strip()
            ]
            if lines:
                out.append(f"--- slide {i} ---\n" + "\n".join(lines))
        return "\n\n".join(out)


def extract_odt(path: Path, limits: Limits) -> str:
    """OpenDocument text — LibreOffice, Google Docs exports."""
    with safe_zip(path, limits) as zf:
        try:
            xml = zf.read("content.xml")
        except KeyError as exc:
            raise ParseError("not an OpenDocument file: no content.xml") from exc
    root = safe_xml(xml)
    paragraphs = []
    for tag in ("p", "h"):
        for el in root.iter(f"{{{_NS['text']}}}{tag}"):
            line = "".join(el.itertext()).strip()
            if line:
                paragraphs.append(line)
    return "\n\n".join(paragraphs)


def extract_epub(path: Path, limits: Limits) -> str:
    """EPUB — a ZIP of XHTML documents."""
    with safe_zip(path, limits) as zf:
        docs = sorted(
            n for n in zf.namelist()
            if n.lower().endswith((".xhtml", ".html", ".htm"))
        )
        if not docs:
            raise ParseError("not an EPUB: no XHTML documents found")
        parts = []
        for name in docs:
            text = html_to_text(decode(zf.read(name)))
            if text.strip():
                parts.append(text)
        return "\n\n".join(parts)


# ── tier 1: optional libraries ───────────────────────────────────────────────

def extract_pdf(path: Path, limits: Limits) -> str:
    """PDF. Needs a library — the format is far past what stdlib can do.

    Tries PyMuPDF first (fastest, best layout), then pypdf, then pdfminer.
    A scanned PDF yields little or nothing here; `parse_file` detects that and
    reports it rather than returning a near-empty string as if it succeeded.
    """
    try:
        import fitz  # PyMuPDF

        with fitz.open(path) as doc:
            return "\n\n".join(
                f"--- page {i} ---\n{page.get_text()}"
                for i, page in enumerate(doc, 1)
            )
    except ImportError:
        pass

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(
            f"--- page {i} ---\n{page.extract_text() or ''}"
            for i, page in enumerate(reader.pages, 1)
        )
    except ImportError:
        pass

    try:
        from pdfminer.high_level import extract_text as pdfminer_extract

        return pdfminer_extract(str(path))
    except ImportError:
        pass

    raise ParseError(
        "PDF support needs a library. Install one:\n"
        "  pip install pymupdf   (fastest, best layout)\n"
        "  pip install pypdf     (pure Python, lighter)"
    )


def extract_rtf(path: Path, limits: Limits) -> str:
    raw = decode(Path(path).read_bytes())
    try:
        from striprtf.striprtf import rtf_to_text

        return rtf_to_text(raw)
    except ImportError:
        pass
    # Crude but useful: strip control words and groups.
    text = re.sub(r"\\'[0-9a-fA-F]{2}", "", raw)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    return re.sub(r"[{}]", "", text).strip()


def extract_doc(path: Path, limits: Limits) -> str:
    """Legacy Word (.doc) — a compound binary, not a ZIP."""
    try:
        import olefile  # noqa: F401
    except ImportError:
        raise ParseError(
            "Legacy .doc support needs a converter. Either:\n"
            "  install LibreOffice and run: soffice --convert-to docx <file>\n"
            "  or re-save the file as .docx"
        ) from None
    raise ParseError(
        "Legacy .doc parsing is unreliable — convert to .docx first:\n"
        "  soffice --convert-to docx <file>"
    )
