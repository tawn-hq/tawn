"""Mistral's document OCR — a purpose-built alternative to generic vision.

Their `/v1/ocr` endpoint takes a whole PDF and returns markdown per page,
preserving headings, tables and reading order. That is better than sending page
images to a general chat model, which has to infer structure from pixels: one
request instead of one per page, and layout that survives.

It sits inside tier 3 because it is a paid cloud call, and it is tried before
the generic vision path when a Mistral key exists.
"""

from __future__ import annotations

import base64
from pathlib import Path

from tawn.parsing.harness import Limits, ParseError

OCR_URL = "https://api.mistral.ai/v1/ocr"
OCR_MODEL = "mistral-ocr-latest"
#: Their documented per-request ceiling.
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
MAX_PAGES = 1000
REQUEST_TIMEOUT = 180


def api_key(home: Path | None = None) -> str | None:
    """The Mistral key, from the environment or the OS keyring."""
    import os

    key = os.environ.get("MISTRAL_API_KEY")
    if key:
        return key
    try:
        import keyring

        return keyring.get_password("tawn", "mistral")
    except Exception:
        return None


def available(home: Path | None = None) -> bool:
    return bool(api_key(home))


def _payload(path: Path, fmt: str) -> dict:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    if fmt == "pdf":
        return {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{data}",
        }
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = {"jpg": "jpeg", "tif": "tiff"}.get(suffix, suffix)
    return {"type": "image_url", "image_url": f"data:image/{mime};base64,{data}"}


def ocr_document(
    path: Path,
    limits: Limits,
    home: Path | None = None,
    key: str | None = None,
    http=None,
) -> str:
    """Read a PDF or image through Mistral OCR, returning markdown.

    `http` is injected in tests so the whole path is exercised without a
    network or a key.
    """
    from tawn.parsing import detect_format

    p = Path(path)
    fmt = detect_format(p)
    if fmt not in ("pdf", "image"):
        raise ParseError(f"Mistral OCR reads PDFs and images, not {fmt}")

    size = p.stat().st_size
    if size > MAX_DOCUMENT_BYTES:
        raise ParseError(
            f"{p.name} is {size // (1024 * 1024)}MB, over Mistral OCR's "
            f"{MAX_DOCUMENT_BYTES // (1024 * 1024)}MB limit"
        )

    key = key or api_key(home)
    if not key:
        raise ParseError(
            "no Mistral key — run `tawn key set mistral`, or set MISTRAL_API_KEY"
        )

    if http is None:
        import httpx

        http = httpx

    try:
        resp = http.post(
            OCR_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": OCR_MODEL,
                "document": _payload(p, fmt),
                "include_image_base64": False,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        # Never leak the key through an error message.
        raise ParseError(f"Mistral OCR failed: {str(exc).replace(key, '***')}") from exc

    pages = body.get("pages") or []
    if not pages:
        raise ParseError("Mistral OCR returned no pages")

    out: list[str] = []
    for page in pages[:MAX_PAGES]:
        markdown = (page.get("markdown") or "").strip()
        if not markdown:
            continue
        index = page.get("index")
        header = f"--- page {index + 1} ---\n" if isinstance(index, int) else ""
        out.append(f"{header}{markdown}")

    if not out:
        raise ParseError("Mistral OCR returned no text")
    return "\n\n".join(out)
