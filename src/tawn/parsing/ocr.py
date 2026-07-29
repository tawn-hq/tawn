"""Tier 2 — OCR for scanned pages and images.

Reached only when cheaper extraction produced nothing: a PDF of scanned pages
has no text layer, and an image never does. Tesseract runs locally, costs no
money and sends nothing anywhere, which is why it sits ahead of the model tier
rather than behind it.

Tier 3 (a vision model) exists for what Tesseract genuinely cannot read —
handwriting, complex layouts, diagrams — and is opt-in per call because it is
the only tier that costs money and leaves the machine.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tawn.parsing.harness import Limits, ParseError

#: Pages beyond this are not OCR'd — the cost is linear and a 900-page scan
#: would take an hour.
MAX_OCR_PAGES = 50
#: Tesseract links OpenMP, and its thread pool thrashes badly on ordinary
#: multi-core desktops: a 900x320 image measured 2m23s unconstrained and 4.7s
#: with the pool pinned to one thread — a 30x difference on identical output.
#: Set before every call rather than documented as a tip, because a user who
#: hits the slow path concludes OCR is broken and never finds the workaround.
OMP_THREAD_LIMIT = "1"
#: Rendering DPI. 300 is the usual accuracy/speed sweet spot for Tesseract.
OCR_DPI = 300


def _pin_threads() -> None:
    """Constrain tesseract's OpenMP pool. See OMP_THREAD_LIMIT above."""
    import os

    os.environ.setdefault("OMP_THREAD_LIMIT", OMP_THREAD_LIMIT)


def ocr_available() -> tuple[bool, str]:
    """Whether OCR can run, and what is missing when it cannot."""
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False, "pip install 'tawn[ocr]'"
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return False, "pip install Pillow"
    if shutil.which("tesseract") is None:
        return False, (
            "the tesseract binary is missing — "
            "apt install tesseract-ocr (Debian/Ubuntu), "
            "brew install tesseract (macOS), "
            "or see https://github.com/tesseract-ocr/tesseract"
        )
    return True, ""


def extract_image(path: Path, limits: Limits, lang: str = "eng") -> str:
    """OCR a single image."""
    ok, hint = ocr_available()
    if not ok:
        raise ParseError(f"reading images needs OCR: {hint}")

    _pin_threads()

    import pytesseract
    from PIL import Image

    try:
        with Image.open(path) as img:
            return pytesseract.image_to_string(img, lang=lang).strip()
    except Exception as exc:
        raise ParseError(f"OCR failed: {exc}") from exc


def ocr_pdf(path: Path, limits: Limits, lang: str = "eng") -> str:
    """Rasterise each PDF page and OCR it.

    Used when a PDF's text layer is empty — the signature of a scan. Needs
    PyMuPDF to render, since Tesseract reads images and not PDFs.
    """
    ok, hint = ocr_available()
    if not ok:
        raise ParseError(f"this PDF has no text layer, so it needs OCR: {hint}")

    try:
        import fitz
    except ImportError:
        raise ParseError(
            "OCR of PDFs needs PyMuPDF to render pages: pip install pymupdf"
        ) from None

    _pin_threads()

    import io

    import pytesseract
    from PIL import Image

    pages: list[str] = []
    try:
        with fitz.open(path) as doc:
            total = len(doc)
            for i, page in enumerate(doc, 1):
                if i > MAX_OCR_PAGES:
                    pages.append(
                        f"\n[stopped after {MAX_OCR_PAGES} of {total} pages — "
                        f"OCR cost grows with page count]"
                    )
                    break
                pixmap = page.get_pixmap(dpi=OCR_DPI)
                img = Image.open(io.BytesIO(pixmap.tobytes("png")))
                text = pytesseract.image_to_string(img, lang=lang).strip()
                if text:
                    pages.append(f"--- page {i} (OCR) ---\n{text}")
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(f"OCR failed: {exc}") from exc
    return "\n\n".join(pages)


#: Pages sent to a vision model. Far lower than the OCR cap because each page
#: is an image in a paid request, not a local CPU cycle.
MAX_MODEL_PAGES = 10
#: Rendering DPI for model input. Lower than OCR's: vision models downscale
#: anyway, and a larger image costs more tokens for no accuracy gain.
MODEL_DPI = 150

_VISION_PROMPT = (
    "Transcribe all text in this image exactly as it appears. Preserve "
    "headings, lists, and table structure using markdown. Do not summarise, "
    "explain, or add commentary. If a region is illegible, write [illegible]."
)


def _render_pages(path: Path, fmt: str) -> list[bytes]:
    """PNG bytes per page, for whatever the document is."""
    if fmt != "pdf":
        return [Path(path).read_bytes()]
    try:
        import fitz
    except ImportError:
        raise ParseError(
            "reading a PDF with a model needs PyMuPDF to render its pages: "
            "pip install pymupdf"
        ) from None
    pages: list[bytes] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, 1):
            if i > MAX_MODEL_PAGES:
                break
            pages.append(page.get_pixmap(dpi=MODEL_DPI).tobytes("png"))
    return pages


def model_read(
    path: Path,
    limits: Limits,
    client=None,
    allow_cloud: bool = True,
    home: Path | None = None,
) -> str:
    """Tier 3 — a vision model, for what OCR cannot read.

    Handwriting, complex multi-column layouts, and diagrams defeat Tesseract.
    A vision model reads them.

    This is the only tier that costs money and sends the document off the
    machine, which is why `parse_file` never reaches it without an explicit
    `allow_model=True`. By the time this function runs the decision has been
    made, so it does the work rather than refusing again.
    """
    import base64

    from tawn.parsing import detect_format

    p = Path(path)
    fmt = detect_format(p)
    if fmt not in ("pdf", "image"):
        raise ParseError(f"a vision model cannot help with {fmt} files")

    # A purpose-built document OCR beats a general chat model at this: one
    # request for the whole file instead of one per page, and layout that
    # survives because the service returns markdown rather than inferring
    # structure from pixels.
    if client is None:
        from tawn.parsing import mistral_ocr

        if mistral_ocr.available(home):
            try:
                return mistral_ocr.ocr_document(p, limits, home=home)
            except ParseError:
                # Fall through to generic vision rather than giving up.
                pass

    if client is None:
        from tawn.home import tawn_home
        from tawn.model.router import default_router

        try:
            client = default_router(Path(home) if home else tawn_home())
        except Exception as exc:
            raise ParseError(f"no model available: {exc}") from exc

    try:
        pages = _render_pages(p, fmt)
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(f"could not render the document: {exc}") from exc

    if not pages:
        raise ParseError("nothing to read")

    from tawn.model.types import Message

    out: list[str] = []
    for i, png in enumerate(pages, 1):
        encoded = base64.b64encode(png).decode("ascii")
        message = Message(
            role="user",
            content=_VISION_PROMPT,
            images=[{"media_type": "image/png", "data": encoded}],
        )
        try:
            resp = client.complete([message], sensitive=not allow_cloud)
        except Exception as exc:
            # Partial output beats none: pages already read are still useful,
            # and the failure is reported rather than hidden.
            if out:
                out.append(f"\n[stopped at page {i}: {exc}]")
                break
            raise ParseError(f"the model could not read this: {exc}") from exc
        text = (resp.text or "").strip()
        if text:
            header = f"--- page {i} (model) ---\n" if fmt == "pdf" else ""
            out.append(f"{header}{text}")

    if not out:
        raise ParseError("the model returned no text for this document")
    return "\n\n".join(out)
