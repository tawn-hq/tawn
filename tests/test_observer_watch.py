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
