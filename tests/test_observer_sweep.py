"""The sweep reconciles the observer's record against reality.

Real temporary git repositories, not mocked `git log` output: the parsing is the
thing under test, and a mock would only test the mock.
"""

import datetime
import json
import subprocess

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession

from tawn.memory.schema import Base, FileSnapshot, ObservedEvent, ObserverWatermark
from tawn.observer import sweep as sw
from tawn.observer.attribution import Attribution
from tawn.observer.projects import Project
from tawn.observer.sessions import record_event

NOW = datetime.datetime(2026, 7, 31, 12, 0, tzinfo=datetime.timezone.utc)


def _db():
    e = create_engine("sqlite://")
    Base.metadata.create_all(e)
    return SASession(e)


def _home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "grants.yaml").write_text("read: []\nwrite: []\nobserve: [fs, git, agents]\n")
    return home


def _git(root, *args, author=None):
    env_args = []
    if author:
        env_args = ["-c", f"user.name={author[0]}", "-c", f"user.email={author[1]}"]
    subprocess.run(
        ["git", "-C", str(root), *env_args, *args],
        check=True, capture_output=True,
    )


def _repo(tmp_path, name="proj"):
    root = tmp_path / name
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Test User")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "commit.gpgsign", "false")
    return Project(root=root, name=name, is_git=True)


def _commit(proj, path, body, msg, author=None):
    (proj.root / path).write_text(body)
    _git(proj.root, "add", "-A")
    args = ["commit", "-q", "-m", msg]
    if author:
        args = ["-c", f"user.name={author[0]}", "-c", f"user.email={author[1]}", *args]
        subprocess.run(["git", "-C", str(proj.root), *args], check=True, capture_output=True)
    else:
        _git(proj.root, *args)


def _watched(s, home, proj):
    """Put a project past its baseline sweep, so later changes are reported.

    A first sweep deliberately records nothing — it establishes what "before"
    means. Every test about detecting a change therefore starts from here.
    """
    sw.sweep_project(s, home, proj, now=NOW)
    s.query(ObservedEvent).delete()
    s.commit()


pytestmark = pytest.mark.skipif(
    subprocess.run(["which", "git"], capture_output=True).returncode != 0,
    reason="git not available",
)


# ── commits ───────────────────────────────────────────────────────────────────


def test_agent_commit_attributes_to_the_agent(tmp_path):
    s, home, proj = _db(), _home(tmp_path), _repo(tmp_path)
    _commit(proj, "seed.py", "0\n", "chore: seed")
    _watched(s, home, proj)
    _commit(proj, "a.py", "x = 1\n", "feat: add a",
            author=("Claude", "noreply@anthropic.com"))

    res = sw.sweep_project(s, home, proj, now=NOW)

    ev = s.query(ObservedEvent).one()
    assert ev.actor == "agent:claude"
    assert ev.confidence == "high"
    assert ev.basis == sw.SWEEP_COMMIT
    assert res.commits_read == 1


def test_human_commit_attributes_to_human(tmp_path):
    s, home, proj = _db(), _home(tmp_path), _repo(tmp_path)
    _commit(proj, "seed.py", "0\n", "chore: seed")
    _watched(s, home, proj)
    _commit(proj, "a.py", "x = 1\n", "feat: add a")

    sw.sweep_project(s, home, proj, now=NOW)

    ev = s.query(ObservedEvent).filter(ObservedEvent.basis == sw.SWEEP_COMMIT).one()
    assert ev.actor == "human"
    assert ev.confidence == "high"


def test_commit_line_counts_are_real_not_file_length(tmp_path):
    """`--numstat` knows removals; the live watcher cannot."""
    s, home, proj = _db(), _home(tmp_path), _repo(tmp_path)
    _commit(proj, "a.py", "1\n2\n3\n4\n5\n", "feat: five lines")
    _watched(s, home, proj)

    _commit(proj, "a.py", "1\n2\n", "refactor: cut to two")
    sw.sweep_project(s, home, proj, now=NOW)

    ev = s.query(ObservedEvent).filter(ObservedEvent.basis == sw.SWEEP_COMMIT).one()
    assert ev.lines_removed == 3
    assert ev.lines_added == 0


def test_second_sweep_with_no_change_writes_nothing(tmp_path):
    s, home, proj = _db(), _home(tmp_path), _repo(tmp_path)
    _commit(proj, "seed.py", "0\n", "chore: seed")
    _watched(s, home, proj)
    _commit(proj, "a.py", "x = 1\n", "feat: a")

    first = sw.sweep_project(s, home, proj, now=NOW)
    before = s.query(ObservedEvent).count()
    second = sw.sweep_project(s, home, proj, now=NOW)

    assert first.changed
    assert not second.changed
    assert s.query(ObservedEvent).count() == before


def test_first_sweep_does_not_backfill_history(tmp_path):
    """Measured on a real repository: backfilling filed 1,613 file events from
    198 commits of history under a single present-day session."""
    s, home, proj = _db(), _home(tmp_path), _repo(tmp_path)
    for i in range(5):
        _commit(proj, f"f{i}.py", f"line {i}\n", f"feat: file {i}")

    res = sw.sweep_project(s, home, proj, now=NOW)

    assert res.commits_read == 0
    assert s.query(ObservedEvent).count() == 0
    assert "baseline" in res.reason


def test_rewritten_history_falls_back_instead_of_failing(tmp_path):
    """`git log <unreachable>..HEAD` errors; a rebase must not break the sweep."""
    s, home, proj = _db(), _home(tmp_path), _repo(tmp_path)
    _commit(proj, "a.py", "x = 1\n", "feat: a")
    s.add(ObserverWatermark(
        project=proj.name, last_commit="0" * 40, tree_digest=None, swept_at=NOW,
    ))
    s.commit()

    res = sw.sweep_project(s, home, proj, now=NOW)

    assert "history rewritten" in res.reason
    assert s.query(ObservedEvent).count() >= 1


# ── working tree ──────────────────────────────────────────────────────────────


def test_uncommitted_change_without_corroboration_is_unknown(tmp_path):
    """No commit and no session log means no evidence — never a timing guess."""
    s, home, proj = _db(), _home(tmp_path), _repo(tmp_path)
    _commit(proj, "a.py", "x = 1\n", "feat: a")
    _watched(s, home, proj)
    (proj.root / "a.py").write_text("x = 1\ny = 2\n")

    sw.sweep_project(s, home, proj, now=NOW)

    tree = s.query(ObservedEvent).filter(
        ObservedEvent.basis.in_([sw.SWEEP_TREE, sw.SWEEP_SCAN])
    ).all()
    assert tree, "the uncommitted edit should be recorded"
    assert all(e.actor == "unknown" and e.confidence == "low" for e in tree)


# ── dedup ─────────────────────────────────────────────────────────────────────


def test_a_path_the_watcher_already_recorded_is_not_duplicated(tmp_path):
    s, home, proj = _db(), _home(tmp_path), _repo(tmp_path)
    _commit(proj, "seed.py", "0\n", "chore: seed")
    _watched(s, home, proj)
    _commit(proj, "a.py", "x = 1\n", "feat: a")
    record_event(
        s, proj.name, str(proj.root / "a.py"), "modified",
        Attribution("agent:claude_code", "high", "session"), NOW,
        lines_added=1, lines_removed=0,
    )

    res = sw.sweep_project(s, home, proj, now=NOW)

    rows = s.query(ObservedEvent).filter(
        ObservedEvent.path == str(proj.root / "a.py"),
        ObservedEvent.kind == "modified",
    ).all()
    assert len(rows) == 1, "one change must not become two rows"
    assert res.skipped_existing >= 1


def test_better_deltas_update_the_row_and_keep_the_original_basis(tmp_path):
    """The record should say who saw it first, with the best numbers available."""
    s, home, proj = _db(), _home(tmp_path), _repo(tmp_path)
    _commit(proj, "a.py", "1\n2\n3\n4\n5\n", "feat: five")
    _watched(s, home, proj)

    (proj.root / "a.py").write_text("1\n2\n")
    row = record_event(
        s, proj.name, str(proj.root / "a.py"), "modified",
        Attribution("agent:claude_code", "high", "session"), NOW,
        lines_added=2, lines_removed=0,   # live watcher: file length, no removals
    )
    s.query(ObserverWatermark).delete()
    s.commit()

    res = sw.sweep_project(s, home, proj, now=NOW)
    s.refresh(row)

    assert res.events_updated >= 1
    assert row.lines_removed == 3, "the sweep's real numbers should win"
    assert row.basis == "session", "but not rewrite who observed it"


# ── snapshot scan (git-independent) ───────────────────────────────────────────


def test_first_scan_takes_a_baseline_rather_than_inventing_changes(tmp_path):
    """No prior snapshot means no "before" — an editor's first index is not a
    changelog, and calling every existing file "added" would be false."""
    s, home = _db(), _home(tmp_path)
    root = tmp_path / "plain"
    root.mkdir()
    (root / "note.md").write_text("one\ntwo\n")
    proj = Project(root=root, name="plain", is_git=False)

    res = sw.sweep_project(s, home, proj, now=NOW)

    assert "baseline" in res.reason
    assert s.query(ObservedEvent).count() == 0
    assert s.query(FileSnapshot).count() == 1


def test_non_git_project_is_covered_by_the_scan(tmp_path):
    """The reason the scan exists — `certin/docs` has no repository."""
    s, home = _db(), _home(tmp_path)
    root = tmp_path / "plain"
    root.mkdir()
    (root / "note.md").write_text("one\ntwo\n")
    proj = Project(root=root, name="plain", is_git=False)
    sw.sweep_project(s, home, proj, now=NOW)          # baseline

    (root / "new.md").write_text("fresh\n")
    res = sw.sweep_project(s, home, proj, now=NOW)

    assert "not a git repository" in res.reason
    ev = s.query(ObservedEvent).one()
    assert ev.path.endswith("new.md")
    assert ev.basis == sw.SWEEP_SCAN
    assert ev.kind == "added"


def test_touch_without_content_change_records_nothing(tmp_path):
    """The false positive the second stage exists to suppress."""
    import os

    s, home = _db(), _home(tmp_path)
    root = tmp_path / "plain"
    root.mkdir()
    f = root / "note.md"
    f.write_text("same\n")
    proj = Project(root=root, name="plain", is_git=False)
    sw.sweep_project(s, home, proj, now=NOW)
    before = s.query(ObservedEvent).count()

    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns + 10**9, st.st_mtime_ns + 10**9))

    res = sw.sweep_project(s, home, proj, now=NOW)

    assert s.query(ObservedEvent).count() == before
    assert not res.changed


def test_real_content_change_is_recorded_with_a_net_delta(tmp_path):
    s, home = _db(), _home(tmp_path)
    root = tmp_path / "plain"
    root.mkdir()
    f = root / "note.md"
    f.write_text("a\nb\nc\n")
    proj = Project(root=root, name="plain", is_git=False)
    sw.sweep_project(s, home, proj, now=NOW)
    s.query(ObservedEvent).delete()
    s.commit()

    f.write_text("a\n")
    sw.sweep_project(s, home, proj, now=NOW)

    ev = s.query(ObservedEvent).one()
    assert ev.kind == "modified"
    assert (ev.lines_added, ev.lines_removed) == (0, 2)


def test_deleting_a_file_is_recorded_and_forgotten(tmp_path):
    s, home = _db(), _home(tmp_path)
    root = tmp_path / "plain"
    root.mkdir()
    f = root / "note.md"
    f.write_text("a\n")
    proj = Project(root=root, name="plain", is_git=False)
    sw.sweep_project(s, home, proj, now=NOW)
    s.query(ObservedEvent).delete()
    s.commit()

    f.unlink()
    sw.sweep_project(s, home, proj, now=NOW)

    assert s.query(ObservedEvent).one().kind == "deleted"
    assert s.query(FileSnapshot).count() == 0


def test_excluded_directories_are_not_scanned(tmp_path):
    s, home = _db(), _home(tmp_path)
    root = tmp_path / "plain"
    root.mkdir()
    proj = Project(root=root, name="plain", is_git=False)
    sw.sweep_project(s, home, proj, now=NOW)          # baseline on an empty tree

    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "node_modules" / "pkg" / "x.js").write_text("noise\n")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref\n")
    (root / "real.md").write_text("content\n")

    sw.sweep_project(s, home, proj, now=NOW)

    paths = [e.path for e in s.query(ObservedEvent).all()]
    assert any(p.endswith("real.md") for p in paths)
    assert not any("node_modules" in p or ".git" in p for p in paths)


# ── dry run ───────────────────────────────────────────────────────────────────


def test_dry_run_writes_nothing(tmp_path):
    s, home, proj = _db(), _home(tmp_path), _repo(tmp_path)
    _commit(proj, "seed.py", "0\n", "chore: seed")
    _watched(s, home, proj)
    _commit(proj, "a.py", "x = 1\n", "feat: a")
    before_marks = s.query(ObserverWatermark).one().swept_at

    res = sw.sweep_project(s, home, proj, dry_run=True, now=NOW)

    assert res.events_added > 0, "it should still say what it would do"
    assert s.query(ObservedEvent).count() == 0
    assert s.query(ObserverWatermark).one().swept_at == before_marks


# ── coverage reporting ────────────────────────────────────────────────────────


def test_coverage_line_states_whether_git_was_consulted(tmp_path):
    s, home, proj = _db(), _home(tmp_path), _repo(tmp_path)
    assert "not reconciled" in sw.coverage_line(s, proj.name)

    _commit(proj, "a.py", "x = 1\n", "feat: a")
    sw.sweep_project(s, home, proj, now=NOW)

    assert "reconciled against git" in sw.coverage_line(s, proj.name)


def test_add_then_delete_records_both(tmp_path):
    """Two sweeps, two real events. Path-only dedup against history swallowed the
    deletion — found by running the sweep on a real project, not by a test."""
    s, home = _db(), _home(tmp_path)
    root = tmp_path / "plain"
    root.mkdir()
    proj = Project(root=root, name="plain", is_git=False)
    sw.sweep_project(s, home, proj, now=NOW)          # baseline, empty

    f = root / "note.md"
    f.write_text("hello\n")
    sw.sweep_project(s, home, proj, now=NOW)

    f.unlink()
    sw.sweep_project(s, home, proj, now=NOW)

    kinds = [e.kind for e in s.query(ObservedEvent).order_by(ObservedEvent.id).all()]
    assert kinds == ["added", "deleted"]
    assert s.query(FileSnapshot).count() == 0


# ── transcript attribution ────────────────────────────────────────────────────


def test_transcript_index_attributes_an_old_change(tmp_path):
    """The gap this closes: mtime proximity compares against a session log's
    *current* mtime, so a change made hours ago never correlated. Measured at
    77% of swept events landing as `unknown`."""
    import time

    from tawn.observer.transcripts import attribute_from_index, build_index

    home = _home(tmp_path)
    root = tmp_path / "plain"
    root.mkdir()
    f = root / "edited.py"
    f.write_text("x = 1\n")

    # A transcript recording that an agent touched this exact file, six hours ago.
    long_ago = time.time() - 6 * 3600
    log_dir = tmp_path / "agentlogs"
    log_dir.mkdir()
    stamp = datetime.datetime.fromtimestamp(
        long_ago, datetime.timezone.utc
    ).isoformat()
    (log_dir / "s.jsonl").write_text(
        json.dumps({
            "timestamp": stamp,
            "message": {"content": [
                {"type": "tool_use", "input": {"file_path": str(f)}}
            ]},
        }) + "\n"
    )
    fed = home / "federation" / "adapters"
    fed.mkdir(parents=True)
    (fed / "config.yaml").write_text(
        "sources:\n"
        "  - name: claude-code\n"
        f"    path: {log_dir}\n"
        "    adapter: claude_code\n"
    )

    index = build_index(home, (str(root),))
    assert str(f) in index, "the transcript path should be indexed"
    assert attribute_from_index(index, str(f), long_ago) == ("agent:claude_code", "high")


def test_a_path_no_agent_touched_stays_unknown(tmp_path):
    """Evidence or nothing — never a guess."""
    from tawn.observer.transcripts import attribute_from_index

    assert attribute_from_index({}, "/x/never-seen.py", 0.0) is None


def test_a_touch_outside_the_window_does_not_attribute(tmp_path):
    from tawn.observer.transcripts import Touch, attribute_from_index

    index = {"/x/a.py": [Touch("claude_code", 1000.0)]}
    assert attribute_from_index(index, "/x/a.py", 1000.0) == ("agent:claude_code", "high")
    assert attribute_from_index(index, "/x/a.py", 1000.0 + 99_999) is None


def test_nearest_touch_wins_when_two_agents_edited_one_file(tmp_path):
    from tawn.observer.transcripts import Touch, attribute_from_index

    index = {"/x/a.py": [Touch("codex", 1000.0), Touch("claude_code", 1900.0)]}
    actor, _ = attribute_from_index(index, "/x/a.py", 1850.0)
    assert actor == "agent:claude_code"


def test_a_path_inside_a_shell_command_is_indexed(tmp_path):
    """Agents edit through shell as often as through a file tool, so the path
    arrives embedded in a command rather than as a `file_path` value. Whole-string
    matching missed those and left recent edits attributed to nobody."""
    import time

    from tawn.observer.transcripts import build_index

    home = _home(tmp_path)
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "app.py"
    target.write_text("x = 1\n")

    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    log_dir = tmp_path / "agentlogs"
    log_dir.mkdir()
    (log_dir / "s.jsonl").write_text(
        json.dumps({
            "timestamp": stamp,
            "message": {"content": [
                {"type": "tool_use", "input": {"command": f"sed -i s/x/y/ {target}"}}
            ]},
        }) + "\n"
    )
    fed = home / "federation" / "adapters"
    fed.mkdir(parents=True)
    (fed / "config.yaml").write_text(
        f"sources:\n  - name: claude-code\n    path: {log_dir}\n    adapter: claude_code\n"
    )

    index = build_index(home, (str(root),))
    assert str(target) in index


def test_directories_and_bare_roots_are_not_indexed_as_files(tmp_path):
    """The substring match also caught `/root/frontend/` and a trailing line
    continuation. A directory is not a file that was edited."""
    from tawn.observer.transcripts import path_pattern, _paths_in

    root = "/tmp/proj"
    pat = path_pattern((root,))
    out: set[str] = set()
    _paths_in(f"cd {root}/frontend/ && cat {root}/a.py \\\\", (root,), out, pat=pat)
    assert out == {f"{root}/a.py"}
