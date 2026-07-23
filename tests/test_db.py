import json
from datetime import datetime, timezone

from tawn.db import Snapshot, init_db, make_engine, session


def test_snapshot_roundtrip():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    with session(engine) as s:
        s.add(
            Snapshot(
                domain="wealth",
                asof=datetime(2026, 7, 7, tzinfo=timezone.utc),
                state_json=json.dumps({"total_ngn": "1000000"}),
            )
        )
        s.commit()
        row = s.query(Snapshot).one()
        assert row.domain == "wealth"
        assert json.loads(row.state_json)["total_ngn"] == "1000000"
        assert row.id is not None


def test_make_engine_uses_settings_default(monkeypatch):
    monkeypatch.setenv("TAWN_DB_URL", "sqlite+pysqlite:///:memory:")
    engine = make_engine()
    assert "sqlite" in str(engine.url)
