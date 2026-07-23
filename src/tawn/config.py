"""Tawn settings. DSN default is peer-auth over the local socket on
Linux/macOS (no host, no password — nothing secret to store, governance
§8). Windows has no Unix domain sockets, so it defaults to a local TCP
connection instead — see `_default_db_url()`."""

import platform

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_db_url() -> str:
    if platform.system() == "Windows":
        return "postgresql+psycopg://tawn:tawn@localhost/tawn"
    return "postgresql+psycopg:///tawn"


class TawnSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TAWN_")

    db_url: str = Field(default_factory=_default_db_url)


def settings() -> TawnSettings:
    """Fresh read every call so env overrides (and tests) always apply."""
    return TawnSettings()
