"""The observer's watch loop.

Mirrors FederationWatcher's shape: pass `event_queue` to inject fake file
events in tests (str = path, None = stop); without one it uses watchfiles for
real inotify/poll. Keeping the loop out of the handler means every behaviour
worth testing is reachable without touching a real filesystem watcher.
"""

from __future__ import annotations

import datetime
import queue
import threading
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from tawn.capability.grants import Grants
from tawn.ignore import load_ignore_patterns, should_ignore
from tawn.observer.attribution import (
    RecentWrite,
    agent_sessions_touched,
    attribute,
    git_identity_for,
)
from tawn.observer.config import load_observer_config
from tawn.observer.projects import Project, discover_projects, tier_enabled
from tawn.observer.sessions import (
    close_idle_sessions,
    close_session,
    current_session,
    record_event,
)

#: How many recent writes the timing heuristic looks back over. Bounded because
#: the list is scanned per event and only the last few seconds ever matter.
_RECENT_CAP = 64


class ObserverWatcher:
    def __init__(
        self,
        home: Path,
        session_factory: Callable[[], Session],
        event_queue: "queue.Queue | None" = None,
    ):
        self.home = Path(home)
        self._session_factory = session_factory
        self._queue = event_queue
        self._stop_event = threading.Event()
        self._recent: list[RecentWrite] = []
        self.reload()

    # ── configuration ────────────────────────────────────────────────────
    def reload(self) -> None:
        self.grants = Grants.load(self.home / "grants.yaml")
        self.cfg = load_observer_config(self.home)
        self.projects = discover_projects(self.grants)
        self._ignore = load_ignore_patterns(self.home)

    @property
    def enabled(self) -> bool:
        return bool(self.grants.observe) and bool(self.projects)

    def project_for(self, path: Path) -> Project | None:
        best: Project | None = None
        for p in self.projects:
            try:
                path.relative_to(p.root)
            except ValueError:
                continue
            # Deepest matching root wins, so a granted subdirectory of another
            # granted directory files its events under the more specific one.
            if best is None or len(p.root.parts) > len(best.root.parts):
                best = p
        return best

    # ── one event ────────────────────────────────────────────────────────
    def handle(
        self, path: Path, kind: str, now: datetime.datetime | None = None
    ) -> None:
        if not self.enabled:
            return
        path = Path(path)
        project = self.project_for(path)
        if project is None:
            return
        dirs, globs, abs_paths = self._ignore
        if should_ignore(path, dirs, globs, abs_paths):
            return

        now = now or datetime.datetime.now(datetime.timezone.utc)
        ts = now.timestamp()
        added, removed = self._deltas(path, kind)

        git_id = (
            git_identity_for(project, str(path))
            if kind == "commit" and tier_enabled(self.grants, "git")
            else None
        )
        hits = (
            agent_sessions_touched(self.home, project, ts, self.cfg)
            if tier_enabled(self.grants, "agents")
            else None
        )
        attr = attribute(
            project=project,
            path=str(path),
            kind=kind,
            ts=ts,
            grants=self.grants,
            cfg=self.cfg,
            recent=list(self._recent),
            git_identity=git_id,
            agent_hits=hits,
        )

        session = self._session_factory()
        record_event(
            session,
            project.name,
            str(path),
            kind,
            attr,
            now,
            lines_added=added,
            lines_removed=removed,
        )
        if kind == "commit":
            sess = current_session(session, project.name)
            if sess is not None:
                close_session(session, sess, now, "commit")

        self._recent.append(RecentWrite(str(path), ts, added, removed))
        del self._recent[:-_RECENT_CAP]

    def _deltas(self, path: Path, kind: str) -> tuple[int, int]:
        """Line counts only — never content.

        A modified file reports its current length as added, which is enough to
        size a change without keeping a copy of it.
        """
        if kind == "deleted":
            return 0, 0
        try:
            with path.open("rb") as fh:
                return sum(1 for _ in fh), 0
        except OSError:
            return 0, 0

    def tick(self, now: datetime.datetime | None = None) -> None:
        now = now or datetime.datetime.now(datetime.timezone.utc)
        session = self._session_factory()
        close_idle_sessions(session, self.cfg, now)

    # ── loops ────────────────────────────────────────────────────────────
    def stop(self) -> None:
        self._stop_event.set()
        if self._queue is not None:
            self._queue.put(None)

    def run(self) -> None:
        if self._queue is not None:
            self._run_from_queue()
        else:
            self._run_watchfiles()

    def _safe_handle(self, raw: str) -> None:
        try:
            self.handle(Path(raw), "modified")
        except Exception:
            # One bad path must not end the watch. The alternative is a silent
            # observer that still looks healthy.
            pass

    def _run_from_queue(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                self.tick()
                continue
            if item is None:
                break
            self._safe_handle(item)

    def _run_watchfiles(self) -> None:
        from watchfiles import watch

        roots = [str(p.root) for p in self.projects]
        if not roots:
            return
        for changes in watch(*roots, stop_event=self._stop_event, rust_timeout=5000):
            for _change, raw in changes:
                self._safe_handle(raw)
            self.tick()


