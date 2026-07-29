"""Content-level ingest filtering.

Complements the path-level rules in `tawn.ignore`: that module decides which
*files* to look at, this one decides which *text* is worth indexing at all.

Pure functions over strings — no I/O, no model calls, so every rule here is
cheap to test and cheap to run over a large corpus.
"""

from __future__ import annotations

import re

_NOISE_PATTERNS = re.compile(
    r"\[SYSTEM NOTIFICATION\]|<task-notification>|<output-file>|"
    r"<system-reminder>|<command-name>|AUTOMATED.*NOT USER INPUT",
    re.IGNORECASE,
)
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_TRACEBACK_HDR = re.compile(r"Traceback \(most recent call last\):", re.MULTILINE)
_BOX_CHARS = frozenset("│╭╰╮╯├┤❱└┌┐╔╗╚╝╞╡")

_LOCKFILE_HINTS = re.compile(
    r'"lockfileVersion"|"integrity":\s*"sha|^# This file is automatically @generated',
    re.MULTILINE,
)
_TOOL_OUTPUT = re.compile(
    r"^\s*(added|removed|changed|audited)\s+\d+\s+packages|"
    r"^npm (WARN|ERR!)|^warning:.*deprecated|"
    r"^\s*Downloading .*\(\d+[KMG]?B\)",
    re.IGNORECASE | re.MULTILINE,
)
_WORD_RE = re.compile(r"[A-Za-z]{2,}")


def prose_ratio(text: str) -> float:
    """Share of the text that reads as words rather than symbols. 0.0–1.0."""
    if not text:
        return 0.0
    word_chars = sum(len(m.group()) for m in _WORD_RE.finditer(text))
    return word_chars / len(text)


def is_garbage(text: str) -> bool:
    """True if content is mostly noise (system tags, UUID lists, tracebacks, Rich panels).

    Moved from parser.py so that every filtering rule lives in one place.
    """
    if _NOISE_PATTERNS.search(text):
        return True
    uuid_chars = sum(len(m.group()) for m in _UUID_RE.finditer(text))
    if uuid_chars > len(text) * 0.3:
        return True
    lines = [line for line in text.splitlines() if line.strip()]
    if lines:
        box_lines = sum(1 for line in lines if (line.lstrip()[:1] in _BOX_CHARS))
        if box_lines > len(lines) * 0.3:
            return True
    if _TRACEBACK_HDR.search(text) and text.count('  File "') >= 2:
        return True
    return False


def is_low_value(text: str) -> bool:
    """True for content that parses fine but carries no durable meaning.

    Lockfiles, package-manager chatter and minified blobs are all technically
    text; none of them belong in a memory the user reads back. The length
    guards matter: a short note is not low-value merely for being short, so
    the symbol-density rules only apply once there is enough text to judge.
    """
    if _LOCKFILE_HINTS.search(text):
        return True
    if _TOOL_OUTPUT.search(text):
        return True

    stripped = text.strip()
    # Minified / base64 blobs: long, and almost no whitespace.
    if len(stripped) > 200 and (stripped.count(" ") / len(stripped)) < 0.02:
        return True
    if len(stripped) > 80 and prose_ratio(stripped) < 0.25:
        return True
    return False
