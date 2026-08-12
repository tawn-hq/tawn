"""The observer's watch loop.

Mirrors FederationWatcher's shape: pass `event_queue` to inject fake file
events in tests (str = path, None = stop); without one it uses watchfiles for
real inotify/poll. Keeping the loop out of the handler means every behaviour
worth testing is reachable without touching a real filesystem watcher.
"""

from __future__ import annotations

import datetime
import logging
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

_log = logging.getLogger(__name__)

#: Directories whose events are dropped before any per-event work happens.
#: Measured caveat: this does **not** speed up arming — watchfiles' Rust layer
#: walks the tree recursively regardless, so ~14k directories still cost ~15s to
#: establish (15.8s unfiltered vs 14.9s filtered). What it buys is skipping the
#: ignore-rule lookup and stat() for the constant churn under .git and .venv.
WATCH_EXCLUDE_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    "dist", "build", ".next", ".cache", ".idea", "site-packages",
    ".ipynb_checkpoints", ".terraform", "target",
})

#: How many recent writes the timing heuristic looks back over. Bounded because
#: the list is scanned per event and only the last few seconds ever matter.
_RECENT_CAP = 64


class ObserverWatcher:
    def __init__(
        self,
        home: Path,
        session_factory: Callable[[], Session],
        event_queue: "queue.Queue | None" = None,
        on_armed: Callable[[], None] | None = None,
        on_swept: Callable[[str], None] | None = None,
        sweep_on_arm: bool = True,
    ):
        self.home = Path(home)
        self._session_factory = session_factory
        self._queue = event_queue
        self.on_armed = on_armed
        self.on_swept = on_swept
        self.sweep_on_arm = sweep_on_arm
        self._stop_event = threading.Event()
        self._recent: list[RecentWrite] = []
        #: Surfaced by `tawn observe status`, so a watcher that is running but
        #: failing is distinguishable from one with nothing to do.
        self.handle_errors = 0
        self.last_error: str | None = None
        self.armed = False
        #: Outcome of the arm-time sweep, surfaced for the same reason as
        #: `handle_errors`: a reconciliation that silently failed leaves a watcher
        #: that looks complete and is not.
        self.sweep_summary: str | None = None
        self.sweep_error: str | None = None
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
        except Exception as exc:
            # One bad path must not end the watch — but it must not be invisible
            # either. Swallowing this cost real debugging time once: `handle()`
            # failing left an observer that printed "watching", recorded nothing,
            # and looked perfectly healthy. Count and surface instead.
            self.handle_errors += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            _log.warning("observer could not record %s: %s", raw, self.last_error)

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

    def _sweep_now(self) -> None:
        """Reconcile against git and the filesystem snapshot.

        Runs once, just after the watch is established, because that is exactly
        the gap it exists to close: the ~15s of recursive-watch setup, plus
        however long the daemon was stopped before this run.

        Non-fatal by design. A reconciliation that cannot run must leave a working
        watcher behind, so the failure is recorded and surfaced rather than raised.
        """
        from tawn.observer.sweep import sweep

        try:
            session = self._session_factory()
            results = sweep(session, self.home)
            added = sum(r.events_added for r in results)
            updated = sum(r.events_updated for r in results)
            self.sweep_summary = (
                f"reconciled {len(results)} project(s): "
                f"+{added} event(s), {updated} corrected"
            )
            _log.info("observer %s", self.sweep_summary)
        except Exception as exc:
            self.sweep_error = f"{type(exc).__name__}: {exc}"
            self.sweep_summary = f"reconciliation failed — {self.sweep_error}"
            _log.warning("observer sweep failed: %s", self.sweep_error)
        if self.on_swept:
            try:
                self.on_swept(self.sweep_summary or "")
            except Exception:
                pass

    def _start_arm_sweep(self) -> None:
        """Sweep off the watch loop.

        Measured at several seconds across four projects. Running it inline would
        stall event consumption immediately after arming — reopening a smaller
        version of the window the sweep is meant to close.
        """
        if not self.sweep_on_arm:
            return
        threading.Thread(
            target=self._sweep_now, name="tawn-observer-sweep", daemon=True
        ).start()

    def _watch_filter(self, _change, path: str) -> bool:
        """Whether watchfiles should report this path at all.

        A coarse pre-filter, not a replacement for the user's ignore rules —
        `should_ignore` still runs per event in `handle()`. This only avoids doing
        that lookup for the constant churn under `.git`, `.venv` and friends.
        """
        parts = set(Path(path).parts)
        return not (parts & WATCH_EXCLUDE_DIRS)

    def _run_watchfiles(self) -> None:
        from watchfiles import watch

        roots = [str(p.root) for p in self.projects]
        if not roots:
            return
        # `yield_on_timeout` is what makes readiness observable: without it the
        # generator only yields on a real change, so there is no way to tell an
        # armed-but-quiet watcher from one still walking the tree. Establishing the
        # recursive watch takes ~15s over a few thousand directories, and
        # announcing readiness before then is what made early edits appear lost.
        it = watch(
            *roots,
            stop_event=self._stop_event,
            rust_timeout=1000,
            yield_on_timeout=True,
            watch_filter=self._watch_filter,
        )
        for changes in it:
            if not self.armed:
                self.armed = True
                if self.on_armed:
                    self.on_armed()
                self._start_arm_sweep()
            for _change, raw in changes:
                self._safe_handle(raw)
            self.tick()


