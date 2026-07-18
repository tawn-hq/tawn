"""Tawn settings. DSN default is peer-auth over the local socket:
no host, no password — nothing secret to store (governance §8)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class TawnSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TAWN_")

    db_url: str = "postgresql+psycopg:///tawn"


def settings() -> TawnSettings:
    """Fresh read every call so env overrides (and tests) always apply."""
    return TawnSettings()
