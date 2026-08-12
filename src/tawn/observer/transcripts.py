"""Which agent touched which file, read from the agents' own transcripts.

The mtime-proximity heuristic in `attribution.agent_sessions_touched` can only
work in real time. It compares a file's mtime against a session log's *current*
mtime, and an active log's mtime is always ~now — so a change made an hour ago
never correlates. Measured: a file edited 774 minutes earlier returned no hits,
while the same call against `now` returned `claude_code`. That made 77% of swept
events `unknown`.

This reads the transcripts instead. Claude Code, Codex and Gemini CLI all write
JSONL containing the paths they operated on, with timestamps — so "this agent
edited this exact file at this time" is available as *evidence* rather than
inferred from two clocks being close together. It works retroactively, which is
precisely what reconciliation needs.

Deliberately format-agnostic: each record is walked for a timestamp and for
strings that look like absolute paths. Three bespoke parsers would be three
things to break when a vendor changes their schema, and the shape being relied on
here — "a path appears in a record that has a time" — is stable across all of
them.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

#: Keys that carry a record's time, in the order they are preferred.
_TS_KEYS = ("timestamp", "ts", "lastUpdated", "startTime", "time", "created_at")

#: Nesting depth for the path hunt. Tool calls sit two or three levels down; going
#: deeper costs time and finds nothing but payload noise.
_MAX_DEPTH = 6

#: Skip transcripts larger than this. A 16 MB session log parsed on every sweep
#: costs more than the attribution is worth, and its recent activity is in the
#: newer, smaller files anyway.
MAX_TRANSCRIPT_BYTES = 24_000_000

#: How far back to read. A change older than this is not worth attributing, and
#: the bound keeps a first sweep from parsing months of history.
DEFAULT_LOOKBACK_HOURS = 72

#: A change is attributed to an agent when the agent touched that exact path
#: within this window. Far wider than the mtime heuristic's 90s because this is
#: evidence of the specific file, not two timestamps happening to be near.
MATCH_WINDOW_SECONDS = 3600


@dataclass(frozen=True)
class Touch:
    agent: str
    ts: float


def _parse_ts(value) -> float | None:
    if isinstance(value, (int, float)):
        # Milliseconds where the value is far beyond a plausible epoch second.
        return float(value) / 1000 if value > 1e11 else float(value)
    if not isinstance(value, str):
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.timestamp()


def _record_ts(rec: dict) -> float | None:
    for k in _TS_KEYS:
        if k in rec:
            got = _parse_ts(rec[k])
            if got is not None:
                return got
    return None


def path_pattern(roots: tuple[str, ...]) -> re.Pattern | None:
    """Match an absolute path under any root, anywhere inside a string.

    A whole-string prefix test is not enough. Agents edit files through shell
    commands as often as through a file tool, so the path arrives embedded in a
    command — `cat /abs/path`, `python3 - <<PY ... /abs/path ...` — rather than as
    the value of a `file_path` field. Measured: whole-string matching indexed 17
    paths where substring matching finds far more, and left files edited 90
    minutes earlier attributed to nobody.
    """
    if not roots:
        return None
    alt = "|".join(re.escape(r.rstrip("/")) for r in roots)
    # Stop at whitespace and the punctuation that ordinarily delimits a path in
    # prose, JSON or a shell command.
    return re.compile(rf"(?:{alt})/[^\s\"'`,;:*?<>|()\[\]{{}}]+")


def _paths_in(
    node, roots: tuple[str, ...], out: set[str], depth: int = 0, pat=None
) -> None:
    """Collect absolute paths under one of `roots` from an arbitrary JSON node."""
    if depth > _MAX_DEPTH:
        return
    if isinstance(node, str):
        if pat is None:
            if node.startswith("/") and node.startswith(roots):
                out.add(node)
            return
        # Cheap containment test first: most strings in a transcript are prose,
        # and running the regex over all of them costs more than one `in`.
        if any(r in node for r in roots):
            for m in pat.findall(node):
                m = m.rstrip(".,\\")
                # A bare root, a directory, or a trailing line-continuation is not
                # a file that was edited. Require a named leaf with a suffix.
                leaf = m.rsplit("/", 1)[-1]
                if leaf and "." in leaf:
                    out.add(m)
        return
    if isinstance(node, dict):
        for v in node.values():
            _paths_in(v, roots, out, depth + 1, pat)
    elif isinstance(node, list):
        for v in node:
            _paths_in(v, roots, out, depth + 1, pat)


def _transcript_files(home: Path, since: float) -> list[tuple[str, Path]]:
    """`(agent, file)` for transcripts with activity since `since`."""
    from tawn.federation.config import load_config

    found: list[tuple[str, Path]] = []
    try:
        sources = load_config(Path(home))
    except Exception:
        return found
    for src in sources:
        root = Path(src.path).expanduser()
        if not root.exists():
            continue
        agent = src.adapter or src.name
        candidates = [root] if root.is_file() else root.rglob("*")
        for f in candidates:
            try:
                if not f.is_file():
                    continue
                st = f.stat()
                if st.st_mtime < since or st.st_size > MAX_TRANSCRIPT_BYTES:
                    continue
            except OSError:
                continue
            found.append((agent, f))
    return found


def build_index(
    home: Path,
    project_roots: tuple[str, ...],
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    now: float | None = None,
) -> dict[str, list[Touch]]:
    """`path -> [Touch]`, from every agent transcript active in the window.

    Built once per sweep and passed around: parsing megabytes of JSONL per file
    would make reconciliation cost more than the thing it is reconciling.
    """
    import time

    now = now or time.time()
    since = now - lookback_hours * 3600
    index: dict[str, list[Touch]] = {}
    pat = path_pattern(project_roots)

    for agent, f in _transcript_files(Path(home), since):
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or len(line) > 2_000_000:
                        continue
                    try:
                        rec = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if not isinstance(rec, dict):
                        continue
                    ts = _record_ts(rec)
                    if ts is None or ts < since:
                        continue
                    hits: set[str] = set()
                    _paths_in(rec, project_roots, hits, pat=pat)
                    for p in hits:
                        index.setdefault(p, []).append(Touch(agent, ts))
        except OSError:
            continue
        except Exception as exc:  # a malformed transcript must not stop the sweep
            _log.warning("transcript %s unreadable: %s", f.name, exc)
    return index


def attribute_from_index(
    index: dict[str, list[Touch]],
    path: str,
    when: float,
    window: int = MATCH_WINDOW_SECONDS,
) -> tuple[str, str] | None:
    """`(actor, confidence)` for a change to `path` at `when`, or None.

    An exact path match is evidence, so it is `high`. The nearest touch in time
    wins when several agents touched the same file — the alternative, listing
    them all, gives the reader no answer at all.
    """
    touches = index.get(path)
    if not touches:
        return None
    best = min(touches, key=lambda t: abs(t.ts - when))
    if abs(best.ts - when) > window:
        return None
    return f"agent:{best.agent}", "high"
