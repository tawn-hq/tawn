import datetime
import queue

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession

from tawn.memory.schema import Base, ObservedEvent, ObserverSession
from tawn.observer.watch import ObserverWatcher

T0 = datetime.datetime(2026, 7, 26, 12, 0, tzinfo=datetime.timezone.utc)


def _factory():
    e = create_engine("sqlite://")
    Base.metadata.create_all(e)
    s = SASession(e)
    return lambda: s, s


def _home(tmp_path, repo, observe="[fs]"):
    (tmp_path / "grants.yaml").write_text(
        f"read: [{repo}]\nwrite: []\nobserve: {observe}\n"
    )
    return tmp_path


def test_no_observe_grant_records_nothing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    f = repo / "a.py"
    f.write_text("x\n")
    factory, s = _factory()
    w = ObserverWatcher(_home(tmp_path, repo, "[]"), factory, event_queue=queue.Queue())
    w.handle(f, "modified", T0)
    assert s.query(ObservedEvent).count() == 0


def test_a_write_under_a_granted_root_is_recorded(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    f = repo / "a.py"
    f.write_text("x\n")
    factory, s = _factory()
    w = ObserverWatcher(_home(tmp_path, repo), factory, event_queue=queue.Queue())
    w.handle(f, "modified", T0)
    ev = s.query(ObservedEvent).one()
    assert ev.project == "repo"
    assert ev.basis == "timing"


def test_paths_outside_every_granted_root_are_ignored(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "elsewhere" / "a.py"
    outside.parent.mkdir()
    outside.write_text("x\n")
    factory, s = _factory()
    w = ObserverWatcher(_home(tmp_path, repo), factory, event_queue=queue.Queue())
    w.handle(outside, "modified", T0)
    assert s.query(ObservedEvent).count() == 0


def test_ignored_paths_are_skipped(tmp_path):
    repo = tmp_path / "repo"
    (repo / "node_modules").mkdir(parents=True)
    f = repo / "node_modules" / "a.js"
    f.write_text("x\n")
    factory, s = _factory()
    w = ObserverWatcher(_home(tmp_path, repo), factory, event_queue=queue.Queue())
    w.handle(f, "modified", T0)
    assert s.query(ObservedEvent).count() == 0


def test_tick_closes_idle_sessions(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    f = repo / "a.py"
    f.write_text("x\n")
    factory, s = _factory()
    w = ObserverWatcher(_home(tmp_path, repo), factory, event_queue=queue.Queue())
    w.handle(f, "modified", T0)
    w.tick(T0 + datetime.timedelta(minutes=25))
    assert s.query(ObserverSession).one().closed_by == "idle"


def test_queue_loop_processes_then_stops(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    f = repo / "a.py"
    f.write_text("x\n")
    q = queue.Queue()
    q.put(str(f))
    q.put(None)
    factory, s = _factory()
    ObserverWatcher(_home(tmp_path, repo), factory, event_queue=q).run()
    assert s.query(ObservedEvent).count() == 1


def test_a_handler_error_does_not_stop_the_loop(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    good = repo / "b.py"
    good.write_text("x\n")
    q = queue.Queue()
    q.put(str(repo / "boom.py"))
    q.put(str(good))
    q.put(None)
    factory, s = _factory()
    w = ObserverWatcher(_home(tmp_path, repo), factory, event_queue=q)
    real = w.handle

    def flaky(path, kind, now=None):
        if path.name == "boom.py":
            raise RuntimeError("kaboom")
        return real(path, kind, now)

    w.handle = flaky
    w.run()
    assert s.query(ObservedEvent).count() == 1


def test_excluded_dirs_are_never_watched(tmp_path):
    """The pre-filter runs inside watchfiles, so excluded trees are not walked.

    Filtering per-event instead is what made arming slow enough to miss the first
    half-minute of edits on a repo containing .venv and node_modules.
    """
    from tawn.observer.watch import ObserverWatcher

    (tmp_path / "grants.yaml").write_text(
        f"read: [{tmp_path}]\nwrite: []\nobserve: [fs]\n"
    )
    w = ObserverWatcher(tmp_path, lambda: None)
    for bad in (".git/HEAD", ".venv/lib/x.py", "node_modules/a/b.js", "__pycache__/m.pyc"):
        assert w._watch_filter(None, str(tmp_path / bad)) is False, bad
    for good in ("src/app.py", "docs/note.md"):
        assert w._watch_filter(None, str(tmp_path / good)) is True, good


def test_handle_failures_are_counted_not_swallowed(tmp_path, monkeypatch):
    """A failing handler must not leave a watcher that looks healthy."""
    from tawn.observer.watch import ObserverWatcher

    (tmp_path / "grants.yaml").write_text(
        f"read: [{tmp_path}]\nwrite: []\nobserve: [fs]\n"
    )
    w = ObserverWatcher(tmp_path, lambda: None)

    def _boom(*a, **k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(w, "handle", _boom)
    w._safe_handle(str(tmp_path / "src" / "app.py"))

    assert w.handle_errors == 1
    assert "db gone" in (w.last_error or "")


def test_armed_is_false_until_the_watch_exists(tmp_path):
    from tawn.observer.watch import ObserverWatcher

    (tmp_path / "grants.yaml").write_text(
        f"read: [{tmp_path}]\nwrite: []\nobserve: [fs]\n"
    )
    assert ObserverWatcher(tmp_path, lambda: None).armed is False


def test_arm_sweep_reconciles_and_reports(tmp_path, monkeypatch):
    """The arming window is exactly what the sweep exists to close, so it runs
    once the watch is established — not before, when there is nothing to catch up
    on, and not never, which was the gap."""
    from tawn.observer.watch import ObserverWatcher
    from tawn.observer import sweep as sw

    (tmp_path / "grants.yaml").write_text(
        f"read: [{tmp_path}]\nwrite: []\nobserve: [fs]\n"
    )
    seen = []
    monkeypatch.setattr(
        sw, "sweep",
        lambda *a, **k: [sw.SweepResult(project="p", events_added=3, events_updated=1)],
    )
    w = ObserverWatcher(tmp_path, lambda: None, on_swept=seen.append)
    w._sweep_now()

    assert w.sweep_error is None
    assert "+3 event(s), 1 corrected" in (w.sweep_summary or "")
    assert seen and "+3 event(s)" in seen[0]


def test_a_failing_sweep_leaves_a_working_watcher(tmp_path, monkeypatch):
    from tawn.observer.watch import ObserverWatcher
    from tawn.observer import sweep as sw

    (tmp_path / "grants.yaml").write_text(
        f"read: [{tmp_path}]\nwrite: []\nobserve: [fs]\n"
    )

    def _boom(*a, **k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(sw, "sweep", _boom)
    w = ObserverWatcher(tmp_path, lambda: None)
    w._sweep_now()          # must not raise

    assert "db gone" in (w.sweep_error or "")
    assert "reconciliation failed" in (w.sweep_summary or "")


def test_sweep_on_arm_can_be_switched_off(tmp_path, monkeypatch):
    from tawn.observer.watch import ObserverWatcher

    (tmp_path / "grants.yaml").write_text(
        f"read: [{tmp_path}]\nwrite: []\nobserve: [fs]\n"
    )
    called = []
    w = ObserverWatcher(tmp_path, lambda: None, sweep_on_arm=False)
    monkeypatch.setattr(w, "_sweep_now", lambda: called.append(1))
    w._start_arm_sweep()

    assert called == []
