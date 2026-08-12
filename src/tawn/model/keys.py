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


def delete_key(provider: str) -> tuple[bool, str | None]:
    """Remove a provider key from the OS keyring.

    Returns `(removed, env_var)`. `env_var` is set when an environment variable
    still supplies the key after deletion — a process cannot unset a variable in
    the shell that launched it, so the honest outcome is to report that the key is
    still live and name what to unset. Silently reporting success while
    `get_key()` keeps returning a value would be the worse failure.
    """
    env_var = f"{provider.upper()}_API_KEY"
    removed = False
    try:
        if keyring.get_password(SERVICE, provider) is not None:
            keyring.delete_password(SERVICE, provider)
            removed = True
    except Exception as exc:
        raise KeyStorageError(
            f"could not remove the {provider} key from the OS keyring: "
            f"{type(exc).__name__}"
        ) from exc
    return removed, (env_var if os.environ.get(env_var) else None)


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
