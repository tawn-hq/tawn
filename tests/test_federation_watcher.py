"""Tests for federation watcher — uses injectable event queue, no real inotify."""
import json
import queue
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tawn.federation.schema import Base as FedBase, FederationRecord
from tawn.federation.config import FedSource
from tawn.federation.watcher import FederationWatcher


@pytest.fixture()
def db_engine(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    FedBase.metadata.create_all(engine)
    return engine


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "tawn"
    (h / "raw" / "imports").mkdir(parents=True)
    (h / "federation" / "inbox").mkdir(parents=True)
    return h


def _make_session_factory(engine):
    def factory():
        return Session(engine)
    return factory


def test_watcher_processes_event_from_queue(home, db_engine):
    eq: queue.Queue = queue.Queue()
    sources = [FedSource(name="claude-code", path=str(home / "federation" / "inbox"),
                         adapter="claude_code")]
    watcher = FederationWatcher(
        home=home,
        sources=sources,
        session_factory=_make_session_factory(db_engine),
        event_queue=eq,
    )

    src = home / "federation" / "inbox" / "session.jsonl"
    src.write_text(json.dumps({"role": "user", "content": "watcher test"}) + "\n")
    eq.put(str(src))
    eq.put(None)  # sentinel to stop

    watcher.run()

    with Session(db_engine) as s:
        records = s.query(FederationRecord).all()
    assert len(records) == 1
    assert records[0].status == "pending"


def test_watcher_ignores_unknown_files(home, db_engine):
    eq: queue.Queue = queue.Queue()
    sources = []
    watcher = FederationWatcher(
        home=home,
        sources=sources,
        session_factory=_make_session_factory(db_engine),
        event_queue=eq,
    )
    unknown = home / "federation" / "inbox" / "image.png"
    unknown.write_bytes(b"\x89PNG")
    eq.put(str(unknown))
    eq.put(None)
    watcher.run()

    with Session(db_engine) as s:
        count = s.query(FederationRecord).count()
    assert count == 0


def test_watcher_skips_duplicate_fingerprint(home, db_engine):
    eq: queue.Queue = queue.Queue()
    sources = []
    watcher = FederationWatcher(
        home=home,
        sources=sources,
        session_factory=_make_session_factory(db_engine),
        event_queue=eq,
    )
    src = home / "federation" / "inbox" / "session.jsonl"
    src.write_text(json.dumps({"role": "user", "content": "dup"}) + "\n")
    eq.put(str(src))
    eq.put(str(src))  # same file twice
    eq.put(None)
    watcher.run()

    with Session(db_engine) as s:
        count = s.query(FederationRecord).count()
    assert count == 1  # not 2


def test_watcher_stop_unblocks(home, db_engine):
    sources = []
    watcher = FederationWatcher(
        home=home,
        sources=sources,
        session_factory=_make_session_factory(db_engine),
        event_queue=queue.Queue(),
    )
    t = threading.Thread(target=watcher.run, daemon=True)
    t.start()
    time.sleep(0.05)
    watcher.stop()
    t.join(timeout=1.0)
    assert not t.is_alive()
