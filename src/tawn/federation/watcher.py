"""Federation watcher — inotify (Linux) or poll, with injectable event queue for tests."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from tawn.federation.config import FedSource, load_config
from tawn.federation.dispatcher import dispatch
from tawn.federation.merge import ingest_file
from tawn.db import make_engine


class FederationWatcher:
    """Watch registered source dirs + inbox; create FederationRecord on new/changed files.

    Pass event_queue to inject fake file events in tests (str = path, None = stop).
    Without event_queue, uses watchfiles for real inotify/poll.
    """

    def __init__(
        self,
        home: Path,
        sources: list[FedSource],
        session_factory: Callable[[], Session],
        event_queue: queue.Queue | None = None,
    ):
        self.home = home
        self.sources = sources
        self._session_factory = session_factory
        self._queue = event_queue
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()
        if self._queue is not None:
            self._queue.put(None)

    def run(self) -> None:
        if self._queue is not None:
            self._run_from_queue()
        else:
            self._run_watchfiles()

    def _run_from_queue(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                break
            self._handle(Path(item))

    def _run_watchfiles(self) -> None:
        from watchfiles import watch

        watch_paths: list[str] = [str(self.home / "federation" / "inbox")]
        for src in self.sources:
            p = Path(src.path).expanduser()
            if p.exists():
                watch_paths.append(str(p))

        for changes in watch(*watch_paths, stop_event=self._stop_event):
            for _, path_str in changes:
                self._handle(Path(path_str))

    def _handle(self, path: Path) -> None:
        adapter = dispatch(path)
        if adapter is None:
            return
        s = self._session_factory()
        try:
            ingest_file(self.home, s, path, source=adapter.name)
        finally:
            s.close()


def make_watcher(
    home: Path,
    event_queue: queue.Queue | None = None,
) -> FederationWatcher:
    """Build a watcher with sources from config + default engine session factory."""
    sources = load_config(home)

    def session_factory() -> Session:
        return Session(make_engine())

    return FederationWatcher(
        home=home,
        sources=sources,
        session_factory=session_factory,
        event_queue=event_queue,
    )
