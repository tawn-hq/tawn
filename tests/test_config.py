from tawn.config import settings


def test_default_dsn_is_peer_auth_socket(monkeypatch):
    # CI sets TAWN_DB_URL job-wide (every test needs a real Postgres to run
    # against) — this test is specifically about the *default* when no env
    # override is present, so it must clear that env var itself rather than
    # relying on it being unset, which only happens to be true locally.
    monkeypatch.delenv("TAWN_DB_URL", raising=False)
    assert settings().db_url == "postgresql+psycopg:///tawn"


def test_env_overrides_dsn(monkeypatch):
    monkeypatch.setenv("TAWN_DB_URL", "sqlite+pysqlite:///:memory:")
    assert settings().db_url == "sqlite+pysqlite:///:memory:"
