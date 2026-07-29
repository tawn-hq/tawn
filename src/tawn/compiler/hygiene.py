"""Entity name and relation-label hygiene.

The LLM extractor is a large improvement on the old Title-cased-words regex,
but it still admits three classes of non-entity, and it phrases the same
relation several different ways. On a real corpus that produced:

  * 4,117 of 17,612 entities that were file paths, IP addresses, hex tokens or
    `Category #hash` codes — including wiki pages for `0x` and `127.0.0.1`;
  * `is located in` / `located_in` / `located in` stored as three distinct
    relations, splitting 1,034 edges across spellings of one idea;
  * `Uniswap`, `uniswap` and `UNISWAP` as three separate entities, because
    resolution matched exactly before falling back to fuzzy.

These are pure functions so the rules are cheap to test and to reuse from both
the live path and a backfill.
"""

from __future__ import annotations

import re

# ── Junk entity detection ─────────────────────────────────────────────────────

_NUMERIC_ONLY = re.compile(r"^[\d.:/\s-]+$")
_HEX_TOKEN = re.compile(r"^0x[0-9a-fA-F]*$|^[0-9a-fA-F]{8,}$")
_PATH_LIKE = re.compile(r"[/\\].*\.[A-Za-z0-9]{1,5}$|^[/~]")
_URL_LIKE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_HASH_SUFFIX = re.compile(r"#[A-Za-z0-9_-]{6,}\s*$")
_SIZE_TOKEN = re.compile(r"^\d+(\.\d+)?\s*[a-zA-Z]{1,3}$")
_DOTTED_MODULE = re.compile(r"^[a-z_]+(\.[a-z_]+){2,}$")


def is_junk_entity(name: str | None) -> bool:
    """True for strings that are not entities a person would look up.

    Deliberately conservative on the keep side: a false reject loses real
    knowledge, while a false accept only adds a page nobody visits.
    """
    if not name:
        return True
    text = name.strip()
    if len(text) < 2:
        return True
    if _NUMERIC_ONLY.match(text):
        return True
    if _HEX_TOKEN.match(text):
        return True
    if _URL_LIKE.match(text):
        return True
    if _PATH_LIKE.search(text):
        return True
    if _HASH_SUFFIX.search(text):
        return True
    if _SIZE_TOKEN.match(text):
        return True
    if _DOTTED_MODULE.match(text):
        return True
    # Needs at least one letter to be a name rather than a code.
    if not re.search(r"[A-Za-z]", text):
        return True
    return False


# ── Relation labels ───────────────────────────────────────────────────────────

_LEADING_COPULA = re.compile(r"^(is|are|was|were|be|being|been)\s+", re.IGNORECASE)


def normalize_relation(relation: str | None) -> str:
    """Collapse spelling variants of one relation into a single label.

    `is_located_in`, `located in` and `IS LOCATED IN` all describe the same
    edge; keeping them distinct fragments the graph so that no relation type
    ever groups.
    """
    if not relation or not relation.strip():
        return "related to"
    text = relation.strip().replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).lower()
    text = _LEADING_COPULA.sub("", text).strip()
    return text or "related to"


# ── Entity identity ───────────────────────────────────────────────────────────

_PUNCT_EDGE = re.compile(r"^[^\w]+|[^\w]+$")


def normalize_entity_name(name: str) -> str:
    """A case- and whitespace-insensitive identity key for an entity.

    Used for lookup, not for display: the stored `canonical` keeps whatever
    casing the source used, so `Open-Meteo` still renders properly while
    `open-meteo` resolves to the same entity.
    """
    text = (name or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return _PUNCT_EDGE.sub("", text)
