import pytest


@pytest.fixture
def tawn_home(tmp_path, monkeypatch):
    """Isolated Tawn home; no test may touch the real ~/.tawn or ~/.claude/projects."""
    home = tmp_path / "tawn-home"
    monkeypatch.setenv("TAWN_HOME", str(home))
    monkeypatch.setenv("TAWN_AGENT_MEMORY_DIR", str(tmp_path / "claude-projects"))
    return home


@pytest.fixture
def db_engine():
    import sqlalchemy as sa

    from tawn.db import init_db

    # StaticPool: one shared in-memory connection, so every thread
    # (e.g. FastAPI TestClient) sees the same database.
    engine = sa.create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=sa.pool.StaticPool,
        connect_args={"check_same_thread": False},
    )
    init_db(engine)
    return engine
