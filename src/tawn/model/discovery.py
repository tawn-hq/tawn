"""Ask providers what models they actually offer.

`PROVIDER_MODELS` is a hardcoded list, so it froze at whenever someone last
edited it: OpenAI offered only `gpt-5.1` in the picker while the live
catalogue had moved on several releases. A curated list cannot keep up with
vendors, and a stale one silently hides models the user is paying for access
to.

So the catalogue is fetched from each provider and cached. The hardcoded list
stays as a fallback for when a provider is unreachable, a key is missing, or
discovery returns nothing — a picker with stale entries beats an empty one.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

# Cache lifetime. Long enough that the picker does not make a network call
# every time it opens, short enough that a new release appears the same day.
CACHE_TTL_SECONDS = 24 * 60 * 60

# Base URLs for the OpenAI-compatible providers. They all implement
# GET /v1/models, so one code path covers seven vendors.
_OPENAI_COMPAT_BASES: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "groq": "https://api.groq.com/openai/v1",
    "grok": "https://api.x.ai/v1",
}

# Substrings marking models that cannot serve a chat completion. Showing them
# in a chat-model picker is noise at best and a confusing failure at worst.
_NON_CHAT_MARKERS = (
    "embedding", "embed", "whisper", "tts", "dall-e", "moderation",
    "image", "audio", "realtime", "transcribe", "rerank", "guard",
)


def _cache_path(home: Path) -> Path:
    return Path(home) / "model_cache.json"


def _read_cache(home: Path) -> dict:
    path = _cache_path(home)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_cache(home: Path, cache: dict) -> None:
    try:
        _cache_path(home).write_text(json.dumps(cache, indent=2))
    except OSError:
        pass  # a cache that cannot be written is not a failure worth raising


def is_chat_model(name: str) -> bool:
    """Whether a model id looks like something you can hold a conversation with."""
    lowered = name.lower()
    return not any(marker in lowered for marker in _NON_CHAT_MARKERS)


def _fetch_openai_compatible(base_url: str, api_key: str) -> list[str]:
    import httpx

    resp = httpx.get(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json().get("data") or []
    return [m["id"] for m in data if isinstance(m, dict) and m.get("id")]


def _fetch_anthropic(api_key: str) -> list[str]:
    import httpx

    resp = httpx.get(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json().get("data") or []
    return [m["id"] for m in data if isinstance(m, dict) and m.get("id")]


def _fetch_gemini(api_key: str) -> list[str]:
    from google import genai

    client = genai.Client(api_key=api_key, http_options={"api_version": "v1", "timeout": 15_000})
    out: list[str] = []
    for m in client.models.list():
        name = (getattr(m, "name", "") or "").removeprefix("models/")
        actions = getattr(m, "supported_actions", None) or []
        # Gemini lists embedding and tuning endpoints alongside chat ones.
        if name and (not actions or "generateContent" in actions):
            out.append(name)
    return out


def fetch_models(provider: str, api_key: str) -> list[str]:
    """Query one provider's catalogue. Raises on network or auth failure."""
    if provider == "anthropic":
        names = _fetch_anthropic(api_key)
    elif provider == "gemini":
        names = _fetch_gemini(api_key)
    elif provider in _OPENAI_COMPAT_BASES:
        names = _fetch_openai_compatible(_OPENAI_COMPAT_BASES[provider], api_key)
    else:
        return []
    return sorted({n for n in names if is_chat_model(n)})


def discover_models(
    provider: str,
    api_key: str,
    home: Path,
    refresh: bool = False,
) -> tuple[list[str], str]:
    """Return (models, source) for a provider.

    `source` is "live", "cache" or "fallback", so a caller can tell the user
    whether they are looking at the real catalogue or a stale stand-in rather
    than presenting all three identically.
    """
    cache = _read_cache(home)
    entry = cache.get(provider) or {}
    fresh = (time.time() - (entry.get("fetched_at") or 0)) < CACHE_TTL_SECONDS

    if not refresh and fresh and entry.get("models"):
        return list(entry["models"]), "cache"

    try:
        models = fetch_models(provider, api_key)
    except Exception:  # noqa: BLE001 — offline is normal, not exceptional
        models = []

    if models:
        cache[provider] = {"models": models, "fetched_at": time.time()}
        _write_cache(home, cache)
        return models, "live"

    # A stale cache still beats nothing.
    if entry.get("models"):
        return list(entry["models"]), "cache"

    from tawn.model.router import PROVIDER_MODELS

    return list(PROVIDER_MODELS.get(provider, [])), "fallback"
