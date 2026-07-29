"""Live model discovery, with cache and fallback."""

import json
import time

import pytest

from tawn.model.discovery import discover_models, fetch_models, is_chat_model


@pytest.mark.parametrize("name", [
    "text-embedding-3-small", "whisper-1", "dall-e-3",
    "tts-1", "gpt-realtime-2.1", "omni-moderation-latest",
])
def test_non_chat_models_are_filtered(name):
    assert is_chat_model(name) is False


@pytest.mark.parametrize("name", ["gpt-5.1", "claude-opus-4-8", "gemini-2.5-pro", "grok-3"])
def test_chat_models_are_kept(name):
    assert is_chat_model(name) is True


def test_live_result_is_cached(tmp_path, monkeypatch):
    import tawn.model.discovery as disc

    calls = []

    def fake_fetch(provider, api_key):
        calls.append(provider)
        return ["gpt-5.6-sol", "gpt-5.5"]

    monkeypatch.setattr(disc, "fetch_models", fake_fetch)

    models, source = discover_models("openai", "key", tmp_path)
    assert models == ["gpt-5.6-sol", "gpt-5.5"]
    assert source == "live"

    models2, source2 = discover_models("openai", "key", tmp_path)
    assert source2 == "cache"
    assert len(calls) == 1, "second call should not hit the network"


def test_refresh_bypasses_cache(tmp_path, monkeypatch):
    import tawn.model.discovery as disc

    calls = []
    monkeypatch.setattr(disc, "fetch_models", lambda p, k: (calls.append(p), ["m"])[1])

    discover_models("openai", "key", tmp_path)
    discover_models("openai", "key", tmp_path, refresh=True)
    assert len(calls) == 2


def test_falls_back_to_curated_list_when_offline(tmp_path, monkeypatch):
    """A picker with stale entries beats an empty one."""
    import tawn.model.discovery as disc

    def boom(provider, api_key):
        raise OSError("network unreachable")

    monkeypatch.setattr(disc, "fetch_models", boom)

    models, source = discover_models("anthropic", "key", tmp_path)
    assert source == "fallback"
    assert "claude-opus-4-8" in models


def test_stale_cache_preferred_over_fallback(tmp_path, monkeypatch):
    """Yesterday's real catalogue is closer to the truth than a hardcoded list."""
    import tawn.model.discovery as disc

    (tmp_path / "model_cache.json").write_text(json.dumps({
        "openai": {"models": ["gpt-5.6-sol"], "fetched_at": time.time() - 10 * 24 * 3600},
    }))
    monkeypatch.setattr(disc, "fetch_models", lambda p, k: (_ for _ in ()).throw(OSError("down")))

    models, source = discover_models("openai", "key", tmp_path)
    assert models == ["gpt-5.6-sol"]
    assert source == "cache"


def test_unknown_provider_returns_nothing(tmp_path):
    assert fetch_models("nonesuch", "key") == []


def test_corrupt_cache_does_not_crash(tmp_path, monkeypatch):
    import tawn.model.discovery as disc

    (tmp_path / "model_cache.json").write_text("{not json")
    monkeypatch.setattr(disc, "fetch_models", lambda p, k: ["m"])

    models, source = discover_models("openai", "key", tmp_path)
    assert models == ["m"]
    assert source == "live"
