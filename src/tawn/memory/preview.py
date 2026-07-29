"""One-line previews for chunks that have no generated summary yet.

Until enrichment reaches a chunk, the feed falls back to its stored text. A
raw slice reads badly: markdown tables collapse into `| a | b | |---|---|`
pipe soup, heading marks leak through, and a fixed byte limit cuts words in
half (`SLA brea`, `` `delegate_to_agent` to ``).

This produces something a person can actually read — prose only, cut at a
sentence or word boundary. It is a display concern, so it never modifies
what is stored.
"""

from __future__ import annotations

import re

_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")
_CODE_MARKER = re.compile(r"\[code:[^\]]*\]")
_BOLD_ITALIC = re.compile(r"(\*\*|__|\*|_|`)")
_BLOCKQUOTE = re.compile(r"^\s*>\s?")
_LIST_MARK = re.compile(r"^\s*([-*+]|\d+\.)\s+")
_WS = re.compile(r"\s+")


def _table_row_to_prose(line: str) -> str:
    """Turn `| a | b |` into `a — b`, dropping separator rows entirely."""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    cells = [c for c in cells if c]
    return " — ".join(cells)


def preview_text(text: str | None, limit: int = 200) -> str:
    """A readable one-line preview, cut on a sentence or word boundary."""
    if not text:
        return ""

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if _TABLE_SEPARATOR.match(line):
            continue  # |---|---| carries no information
        if _TABLE_ROW.match(line):
            line = _table_row_to_prose(line)
        line = _HEADING.sub("", line)
        line = _BLOCKQUOTE.sub("", line)
        line = _LIST_MARK.sub("", line)
        line = _CODE_MARKER.sub("", line)
        line = _BOLD_ITALIC.sub("", line)
        if line.strip():
            lines.append(line.strip())

    out = _WS.sub(" ", " ".join(lines)).strip()
    if not out:
        return ""
    if len(out) <= limit:
        return out

    window = out[: limit + 1]

    # A sentence end inside the last third of the window reads better than a
    # mid-sentence cut, so prefer it when one is close to the limit.
    sentence_end = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if sentence_end >= limit * 0.6:
        return window[: sentence_end + 1].strip()

    cut = window.rfind(" ")
    if cut <= 0:
        cut = limit
    return window[:cut].rstrip(" ,;:—-") + "…"
