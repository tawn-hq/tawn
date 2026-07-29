from pathlib import Path

from tawn.capability.grants import Grants
from tawn.observer.attribution import Attribution, RecentWrite, attribute
from tawn.observer.config import ObserverConfig
from tawn.observer.projects import Project

CFG = ObserverConfig()
P = Project(root=Path("/x"), name="x", is_git=True)
ALL = Grants(observe=["fs", "git", "agents"])


def _attr(**kw):
    base = dict(
        project=P, path="/x/a.py", kind="modified", ts=1000.0,
        grants=ALL, cfg=CFG, recent=[],
    )
    base.update(kw)
    return attribute(**base)


def test_git_agent_author_wins_at_high_confidence():
    a = _attr(
        kind="commit",
        git_identity=("Claude <noreply@anthropic.com>", "Testy <t@e.com>"),
    )
    assert a == Attribution("agent:noreply@anthropic.com", "high", "git")


def test_git_human_author():
    a = _attr(kind="commit", git_identity=("Testy <t@e.com>", "Testy <t@e.com>"))
    assert a == Attribution("human", "high", "git")


def test_agent_session_correlation_attributes_uncommitted_work():
    a = _attr(agent_hits=["claude-code"])
    assert a == Attribution("agent:claude-code", "high", "session")


def test_timing_burst_is_low_confidence_agent():
    recent = [RecentWrite(f"/x/f{i}.py", 999.9, 5, 0) for i in range(4)]
    a = _attr(recent=recent)
    assert a == Attribution("agent:unknown", "low", "timing")


def test_large_single_file_rewrite_is_a_burst():
    a = _attr(recent=[RecentWrite("/x/a.py", 999.9, 80, 60)])
    assert a.actor == "agent:unknown"
    assert a.basis == "timing"


def test_incremental_edit_is_low_confidence_human():
    a = _attr(recent=[RecentWrite("/x/a.py", 900.0, 2, 1)])
    assert a == Attribution("human", "low", "timing")


def test_timing_never_overrides_git():
    """The guard that makes attribution trustworthy: a heuristic guess must not
    outrank evidence."""
    recent = [RecentWrite(f"/x/f{i}.py", 999.9, 5, 0) for i in range(9)]
    a = _attr(
        kind="commit", recent=recent,
        git_identity=("Testy <t@e.com>", "Testy <t@e.com>"),
    )
    assert a == Attribution("human", "high", "git")


def test_timing_never_overrides_session():
    recent = [RecentWrite(f"/x/f{i}.py", 999.9, 5, 0) for i in range(9)]
    a = _attr(recent=recent, agent_hits=["codex"])
    assert a == Attribution("agent:codex", "high", "session")


def test_disabled_tiers_are_skipped():
    a = _attr(
        grants=Grants(observe=["fs"]), kind="commit",
        git_identity=("Claude <noreply@anthropic.com>", "x"),
        agent_hits=["claude-code"],
    )
    assert a.basis == "timing"  # git and agents both off


def test_no_tiers_yields_honest_unknown():
    a = _attr(grants=Grants(observe=[]))
    assert a == Attribution("unknown", "low", "none")
