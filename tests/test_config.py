from tawn.config import settings


def test_default_dsn_is_peer_auth_socket():
    assert settings().db_url == "postgresql+psycopg:///tawn"


def test_env_overrides_dsn(monkeypatch):
    monkeypatch.setenv("TAWN_DB_URL", "sqlite+pysqlite:///:memory:")
    assert settings().db_url == "sqlite+pysqlite:///:memory:"
