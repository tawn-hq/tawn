import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as SASession

from tawn.observer.attribution import Attribution
from tawn.observer.sessions import close_session, current_session, record_event

T0 = datetime.datetime(2026, 7, 26, 12, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture
def client(tawn_home, db_engine):
    """App bound to the shared in-memory engine, plus a session for seeding.

    `Depends(get_session)` builds its own engine from settings, so without the
    override every request would hit the developer's real Postgres.
    """
    tawn_home.mkdir(parents=True, exist_ok=True)
    (tawn_home / "grants.yaml").write_text("read: []\nwrite: []\nobserve: [fs]\n")

    import tawn.db as db_mod
    from tawn.web import create_app

    def _get_session():
        with SASession(db_engine) as s:
            yield s

    app = create_app(db_engine)
    app.dependency_overrides[db_mod.get_session] = _get_session
    return TestClient(app), SASession(db_engine)


def test_sessions_endpoint_reports_attribution(client):
    c, s = client
    record_event(
        s, "tawn", "/x/a.py", "modified",
        Attribution("agent:codex", "high", "session"), T0, 5, 0,
    )
    close_session(s, current_session(s, "tawn"), T0, "commit")
    r = c.get("/api/observer/sessions")
    assert r.status_code == 200
    row = r.json()["sessions"][0]
    assert row["project"] == "tawn"
    assert row["closed_by"] == "commit"
    assert row["attribution"] == "1 agent:codex"


def test_events_endpoint_returns_a_sessions_events(client):
    c, s = client
    record_event(
        s, "tawn", "/x/a.py", "modified", Attribution("human", "high", "git"), T0
    )
    sid = current_session(s, "tawn").id
    r = c.get(f"/api/observer/sessions/{sid}/events")
    assert r.status_code == 200
    assert r.json()["events"][0]["actor"] == "human"


def test_projects_endpoint_is_empty_without_read_grants(client):
    c, _ = client
    r = c.get("/api/observer/projects")
    assert r.status_code == 200
    assert r.json()["projects"] == []


def test_review_closes_and_reports(client):
    c, s = client
    record_event(
        s, "tawn", "/x/a.py", "modified", Attribution("human", "high", "git"), T0
    )
    r = c.post("/api/observer/review", params={"project": "tawn"})
    assert r.status_code == 200
    assert r.json()["closed"] == 1
