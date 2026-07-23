"""Tests for federation config read/write."""
import pytest
from tawn.federation.adapters.base import ConvTurn
from tawn.federation.config import FedSource, load_config, save_config


def test_convturn_defaults():
    t = ConvTurn(role="user", content="hello")
    assert t.role == "user"
    assert t.content == "hello"
    assert t.sensitive is False
    assert t.metadata == {}


def test_load_config_empty(tmp_path):
    home = tmp_path / "tawn"
    home.mkdir()
    sources = load_config(home)
    assert sources == []


def test_save_and_load_config(tmp_path):
    home = tmp_path / "tawn"
    home.mkdir()
    (home / "federation" / "adapters").mkdir(parents=True)
    s = FedSource(name="hermes", path="~/.hermes/", adapter="generic",
                  format="jsonl", added="2026-07-22", auto_detected=False)
    save_config(home, [s])
    loaded = load_config(home)
    assert len(loaded) == 1
    assert loaded[0].name == "hermes"
    assert loaded[0].adapter == "generic"
