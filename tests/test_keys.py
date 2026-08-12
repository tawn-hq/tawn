import pytest

import tawn.model.keys as keys_mod
from tawn.model.keys import KeyStorageError, get_key, key_status, set_key


def test_get_key_prefers_keyring(monkeypatch):
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        keys_mod.keyring, "set_password", lambda svc, user, val: store.__setitem__((svc, user), val)
    )
    monkeypatch.setattr(
        keys_mod.keyring, "get_password", lambda svc, user: store.get((svc, user))
    )
    set_key("gemini", "sk-keyring")
    monkeypatch.setenv("GEMINI_API_KEY", "sk-env")
    assert get_key("gemini") == "sk-keyring"


def test_get_key_falls_back_to_env(monkeypatch):
    monkeypatch.setattr(keys_mod.keyring, "get_password", lambda svc, user: None)
    monkeypatch.setenv("GEMINI_API_KEY", "sk-env")
    assert get_key("gemini") == "sk-env"


def test_get_key_none_when_unset(monkeypatch):
    monkeypatch.setattr(keys_mod.keyring, "get_password", lambda svc, user: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert get_key("gemini") is None


def test_keyring_errors_degrade_to_env(monkeypatch):
    def boom(svc, user):
        raise RuntimeError("no backend")

    monkeypatch.setattr(keys_mod.keyring, "get_password", boom)
    monkeypatch.setenv("GEMINI_API_KEY", "sk-env")
    assert get_key("gemini") == "sk-env"


def test_set_key_verifies_round_trip(monkeypatch):
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        keys_mod.keyring, "set_password", lambda svc, user, val: store.__setitem__((svc, user), val)
    )
    monkeypatch.setattr(
        keys_mod.keyring, "get_password", lambda svc, user: store.get((svc, user))
    )
    set_key("gemini", "sk-new")
    assert store[("tawn", "gemini")] == "sk-new"


def test_set_key_no_backend_raises_key_storage_error(monkeypatch):
    def boom(svc, user, val):
        raise RuntimeError("No recommended backend was available")

    monkeypatch.setattr(keys_mod.keyring, "set_password", boom)
    with pytest.raises(KeyStorageError) as ei:
        set_key("gemini", "sk-SECRET")
    # the error must guide to the env fallback and never echo the key
    assert "GEMINI_API_KEY" in str(ei.value)
    assert "sk-SECRET" not in str(ei.value)


def test_set_key_silent_store_failure_raises(monkeypatch):
    # backend accepts the write but the key can't be read back → not stored
    monkeypatch.setattr(keys_mod.keyring, "set_password", lambda svc, user, val: None)
    monkeypatch.setattr(keys_mod.keyring, "get_password", lambda svc, user: None)
    with pytest.raises(KeyStorageError):
        set_key("gemini", "sk-SECRET")


def test_key_status_never_contains_value(monkeypatch):
    monkeypatch.setattr(keys_mod.keyring, "get_password", lambda svc, user: "sk-SECRET")
    assert "sk-SECRET" not in key_status("gemini")


def test_delete_removes_from_keyring(monkeypatch):
    import tawn.model.keys as k

    store = {("tawn", "openai"): "sk-x"}
    monkeypatch.setattr(k.keyring, "get_password", lambda s, p: store.get((s, p)))
    monkeypatch.setattr(k.keyring, "delete_password", lambda s, p: store.pop((s, p)))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    removed, env_var = k.delete_key("openai")
    assert removed is True
    assert env_var is None
    assert k.get_key("openai") is None


def test_delete_reports_a_key_still_live_in_the_environment(monkeypatch):
    """A process cannot unset a parent shell's variable, so saying "removed"
    without naming the survivor would be a lie the user finds out later."""
    import tawn.model.keys as k

    monkeypatch.setattr(k.keyring, "get_password", lambda s, p: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    removed, env_var = k.delete_key("openai")
    assert removed is False
    assert env_var == "OPENAI_API_KEY"
    assert k.get_key("openai") == "sk-env"   # still live, honestly reported


def test_delete_never_leaks_the_value_in_an_error(monkeypatch):
    import tawn.model.keys as k

    monkeypatch.setattr(k.keyring, "get_password", lambda s, p: "sk-SECRET123")

    def _boom(*a, **kw):
        raise RuntimeError("backend locked")

    monkeypatch.setattr(k.keyring, "delete_password", _boom)
    try:
        k.delete_key("openai")
    except k.KeyStorageError as e:
        assert "sk-SECRET123" not in str(e)
    else:
        raise AssertionError("expected KeyStorageError")
