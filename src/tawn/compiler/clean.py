"""Chunk text cleaning.

Cleaned text is what gets stored, embedded and displayed. The original is
always recoverable from `source_path` on disk, so nothing is lost by not
keeping a second copy in the database.

The bet here: a feed line saying "24 lines of Python" is more useful than
24 lines of Python the user already read in their editor.
"""

from __future__ import annotations

import re

from tawn.compiler.quality import prose_ratio

_FENCE_RE = re.compile(r"^```([A-Za-z0-9_+-]*)[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
_ENVELOPE_RE = re.compile(
    r"<(system-reminder|task-notification|output-file|command-name|command-message)>"
    r".*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_MARKER_RE = re.compile(r"\[code:[^\]]*\]")
_BLANKS_RE = re.compile(r"\n{3,}")
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)


def collapse_code_blocks(text: str) -> str:
    """Replace fenced code blocks with a one-line marker.

    Inline code (single backticks) is left alone — it is usually part of the
    sentence rather than a wall of source.
    """
    def _sub(m: re.Match) -> str:
        lang = m.group(1).strip()
        n = len([line for line in m.group(2).splitlines() if line.strip()])
        return f"[code: {lang}, {n} lines]" if lang else f"[code: {n} lines]"

    return _FENCE_RE.sub(_sub, text)


def clean_chunk(text: str) -> str:
    """Full cleaning pass. Returns "" when nothing meaningful survives."""
    out = _ENVELOPE_RE.sub("", text)
    out = collapse_code_blocks(out)
    out = _TRAILING_WS_RE.sub("", out)
    out = _BLANKS_RE.sub("\n\n", out).strip()

    if not out:
        return ""

    # Nothing but code markers left → the chunk was pure code.
    without_markers = _MARKER_RE.sub("", out).strip()
    if not without_markers:
        return ""
    if len(without_markers) > 40 and prose_ratio(without_markers) < 0.25:
        return ""
    return out
