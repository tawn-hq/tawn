"""Tests for user config store."""
import pytest
from tawn.user_config import (
    load_user_config, save_user_config, get_config_value,
    set_config_value, reset_config_value, all_keys, defaults,
)


def test_load_defaults_when_no_file(tmp_path):
    cfg = load_user_config(tmp_path / "tawn")
    assert cfg["theme"] == "system"
    assert cfg["web_port"] == 8787
    assert cfg["memory_max_mb"] is None


def test_save_and_load_roundtrip(tmp_path):
    home = tmp_path / "tawn"
    home.mkdir()
    cfg = load_user_config(home)
    cfg["theme"] = "dark"
    cfg["web_port"] = 9000
    save_user_config(home, cfg)
    loaded = load_user_config(home)
    assert loaded["theme"] == "dark"
    assert loaded["web_port"] == 9000


def test_config_file_chmod_600(tmp_path):
    import stat
    home = tmp_path / "tawn"
    home.mkdir()
    save_user_config(home, load_user_config(home))
    p = home / "config.yaml"
    assert (p.stat().st_mode & 0o777) == 0o600


def test_get_known_key(tmp_path):
    home = tmp_path / "tawn"
    home.mkdir()
    assert get_config_value(home, "theme") == "system"


def test_get_unknown_key_raises(tmp_path):
    with pytest.raises(KeyError):
        get_config_value(tmp_path / "tawn", "nonexistent")


def test_set_theme(tmp_path):
    home = tmp_path / "tawn"
    home.mkdir()
    v = set_config_value(home, "theme", "dark")
    assert v == "dark"
    assert get_config_value(home, "theme") == "dark"


def test_set_invalid_theme_raises(tmp_path):
    home = tmp_path / "tawn"
    home.mkdir()
    with pytest.raises(ValueError):
        set_config_value(home, "theme", "neon")


def test_set_int_value(tmp_path):
    home = tmp_path / "tawn"
    home.mkdir()
    v = set_config_value(home, "web_port", "9090")
    assert v == 9090


def test_set_null_value(tmp_path):
    home = tmp_path / "tawn"
    home.mkdir()
    set_config_value(home, "memory_max_mb", "256")
    assert get_config_value(home, "memory_max_mb") == 256
    v = set_config_value(home, "memory_max_mb", "null")
    assert v is None


def test_reset_to_default(tmp_path):
    home = tmp_path / "tawn"
    home.mkdir()
    set_config_value(home, "theme", "dark")
    v = reset_config_value(home, "theme")
    assert v == "system"
    assert get_config_value(home, "theme") == "system"


def test_all_keys_complete(tmp_path):
    keys = all_keys()
    assert "theme" in keys
    assert "model" in keys
    assert "memory_max_mb" in keys
    assert "cpu_weight" in keys


def test_defaults_match_load(tmp_path):
    home = tmp_path / "tawn"
    cfg = load_user_config(home)
    for k, v in defaults().items():
        assert cfg[k] == v
