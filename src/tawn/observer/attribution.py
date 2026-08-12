"""Who made this change — the user, or which agent.

Three tiers, tried in order, each gated on its own `observe:` entry. The first
tier returning a `high`-confidence answer wins; a `low`-confidence guess never
overrides evidence. That ordering is the whole contract: attribution that
sounds certain while being wrong is worse than no attribution at all, so the
confidence field is load-bearing and the review template branches on it.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from tawn.capability.grants import Grants
from tawn.observer.config import ObserverConfig
from tawn.observer.projects import Project, tier_enabled

UNKNOWN = "unknown"

#: Bound the walk over a federation source dir — these hold thousands of files
#: and correlation only needs to know whether *any* of them moved recently.
#:
#: Raised from 500 after measuring: `~/.gemini/tmp` holds 2,812 entries, so the
#: old cap examined 18% of them and silently missed that agent whenever its
#: transcripts sorted late. This tier is now a fallback behind
#: `transcripts.build_index`, but a fallback that quietly skips an agent is worse
#: than one that is merely weak.
_SCAN_LIMIT = 20_000


@dataclass(frozen=True)
class Attribution:
    actor: str  # "human" | "agent:<tool>" | "agent:unknown" | "unknown"
    confidence: str  # "high" | "low"
    basis: str  # "git" | "session" | "timing" | "none"


@dataclass(frozen=True)
class RecentWrite:
    path: str
    ts: float
    lines_added: int
    lines_removed: int


def _match_agent_identity(who: str, identities: list[str]) -> str | None:
    low = (who or "").lower()
    for ident in identities:
        if ident.lower() in low:
            return ident
    return None


def git_identity_for(project: Project, path: str) -> tuple[str, str] | None:
    """(author, committer) of HEAD in this project, or None if unavailable."""
    if not project.is_git:
        return None
    try:
        out = subprocess.run(
            [
                "git", "-C", str(project.root), "log", "-1",
                "--format=%an <%ae>%n%cn <%ce>",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    lines = out.stdout.strip().splitlines()
    if out.returncode != 0 or len(lines) < 2:
        return None
    return lines[0], lines[1]


def agent_sessions_touched(
    home: Path, project: Project, ts: float, cfg: ObserverConfig
) -> list[str]:
    """Adapter names whose session logs were written within the window.

    The federation adapters already know where Claude Code, Codex and Gemini
    CLI keep their transcripts, so correlation costs a stat() rather than a
    new integration.
    """
    from tawn.federation.config import load_config

    hits: list[str] = []
    try:
        sources = load_config(Path(home))
    except Exception:
        return hits
    window = cfg.correlation_window_seconds
    for src in sources:
        root = Path(src.path).expanduser()
        if not root.exists():
            continue
        try:
            candidates = [root] if root.is_file() else list(root.rglob("*"))
        except Exception:
            continue
        for f in candidates[:_SCAN_LIMIT]:
            try:
                if f.is_file() and abs(f.stat().st_mtime - ts) <= window:
                    hits.append(src.adapter or src.name)
                    break
            except OSError:
                continue
    return hits


def _is_burst(
    path: str, recent: list[RecentWrite], ts: float, cfg: ObserverConfig
) -> bool:
    window_s = cfg.burst_window_ms / 1000.0
    in_window = [r for r in recent if 0 <= ts - r.ts <= window_s]
    if len({r.path for r in in_window}) >= cfg.burst_files:
        return True
    single_s = cfg.burst_single_ms / 1000.0
    # A whole file replaced in well under a human's editing cadence.
    for r in recent:
        if (
            r.path == path
            and abs(ts - r.ts) <= single_s
            and r.lines_added + r.lines_removed >= cfg.burst_lines
        ):
            return True
    return False


def attribute(
    project: Project,
    path: str,
    kind: str,
    ts: float,
    grants: Grants,
    cfg: ObserverConfig,
    recent: list[RecentWrite],
    git_identity: tuple[str, str] | None = None,
    agent_hits: list[str] | None = None,
) -> Attribution:
    """Attribute one change.

    `git_identity` and `agent_hits` are injected rather than fetched here, so
    this stays a pure function; the watcher supplies them from the helpers
    above.
    """
    # Tier 1 — git identity.
    if kind == "commit" and tier_enabled(grants, "git") and git_identity:
        author, committer = git_identity
        matched = _match_agent_identity(
            author, cfg.agent_identities
        ) or _match_agent_identity(committer, cfg.agent_identities)
        actor = f"agent:{matched}" if matched else "human"
        return Attribution(actor, "high", "git")

    # Tier 2 — agent session correlation. Attributes uncommitted work, which
    # is where agent output lives at the moment it matters.
    if tier_enabled(grants, "agents") and agent_hits:
        return Attribution(f"agent:{agent_hits[0]}", "high", "session")

    # Tier 3 — timing heuristics. Always low confidence, never authoritative.
    if tier_enabled(grants, "fs"):
        if _is_burst(path, recent, ts, cfg):
            return Attribution("agent:unknown", "low", "timing")
        return Attribution("human", "low", "timing")

    return Attribution(UNKNOWN, "low", "none")
