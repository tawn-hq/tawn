"""API keys: OS keyring first, env fallback. Never files, never logs
(governance §8: secrets isolated, never in model context)."""

import os

import keyring

SERVICE = "tawn"


class KeyStorageError(Exception):
    """The OS keyring refused or dropped the key. Message never contains it."""


def _env_hint(provider: str) -> str:
    return (
        f"could not store the {provider} key in the OS keyring. "
        f"Fallback: export {provider.upper()}_API_KEY in your shell profile "
        "(never put keys in files inside the repo or ~/.tawn)."
    )


def set_key(provider: str, value: str) -> None:
    """Store in the OS keyring and verify it reads back. Raises KeyStorageError
    (with env fallback guidance, without the key) when storage isn't safe."""
    try:
        keyring.set_password(SERVICE, provider, value)
        stored = keyring.get_password(SERVICE, provider)
    except Exception as exc:
        raise KeyStorageError(_env_hint(provider)) from exc
    if stored != value:
        raise KeyStorageError(_env_hint(provider))


def get_key(provider: str) -> str | None:
    try:
        stored = keyring.get_password(SERVICE, provider)
    except Exception:
        stored = None  # headless box / no backend — env still works
    return stored or os.environ.get(f"{provider.upper()}_API_KEY")


def key_status(provider: str) -> str:
    """For display: where the key comes from — never the value."""
    try:
        if keyring.get_password(SERVICE, provider):
            return "set (keyring)"
    except Exception:
        pass
    if os.environ.get(f"{provider.upper()}_API_KEY"):
        return "set (env)"
    return "not set"
