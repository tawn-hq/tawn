"""Embedding abstraction — Ollama (nomic-embed-text) → OpenAI → Gemini fallback.

Dims are locked per installation in config.yaml. Changing the model after
first use requires `tawn compile --rebuild`.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

NO_EMBED_WARNING = """\
⚠  No embedding model available — compile skipped.
   Fix one of:
     ollama pull nomic-embed-text        (free, local, recommended)
     ollama pull mxbai-embed-large       (alternative local, 1024 dims)
     ollama pull bge-m3                  (multilingual, 1024 dims)
     ollama pull snowflake-arctic-embed  (strong retrieval, 1024 dims)
     tawn key set openai                 (costs ~$0.0001/1K tokens)
     tawn key set gemini                 (free tier available)
   Then run: tawn compile"""

# Ollama embedding models in priority order (model_name, expected_dims)
_OLLAMA_MODELS: list[tuple[str, int]] = [
    ("nomic-embed-text", 1024),
    ("mxbai-embed-large", 1024),
    ("bge-m3", 1024),
    ("snowflake-arctic-embed", 1024),
    ("all-minilm", 384),
]

_OPENAI_MODEL = "text-embedding-3-small"
_OPENAI_DIMS = 1536
_GEMINI_MODEL = "gemini-embedding-001"  # replaces text-embedding-004 (3072 dims, supports matryoshka)
_GEMINI_DIMS = 768  # request 768 via output_dimensionality for compat


class EmbedError(Exception):
    pass


def _read_config(home: Path) -> dict:
    cfg = home / "config.yaml"
    if cfg.exists():
        return yaml.safe_load(cfg.read_text()) or {}
    return {}


def _write_config(home: Path, data: dict) -> None:
    cfg = home / "config.yaml"
    existing = _read_config(home)
    existing.update(data)
    cfg.write_text(yaml.dump(existing, default_flow_style=False))


def get_embed_config(home: Path) -> tuple[str, int]:
    """Return (embed_model, embed_dims) from config, or ('', 0) if not set."""
    cfg = _read_config(home)
    return cfg.get("embed_model", ""), cfg.get("embed_dims", 0)


def _ollama_embed_model(text: str, model: str) -> list[float]:
    """Embed using a specific Ollama model. Raises EmbedError if not installed."""
    try:
        import ollama as ollama_sdk
        resp = ollama_sdk.embeddings(model=model, prompt=text)
        return resp["embedding"]
    except Exception as exc:
        raise EmbedError(f"ollama/{model}: {exc}") from exc


def _ollama_embed(text: str) -> list[float]:
    """Try each supported Ollama embed model in priority order."""
    last_err: EmbedError | None = None
    for model_name, _ in _OLLAMA_MODELS:
        try:
            return _ollama_embed_model(text, model_name)
        except EmbedError as e:
            last_err = e
    raise EmbedError(f"no Ollama embed model available (last: {last_err})")


def _openai_embed(text: str) -> list[float]:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        try:
            import keyring
            api_key = keyring.get_password("tawn", "openai") or ""
        except Exception:
            pass
    if not api_key:
        raise EmbedError("no OPENAI_API_KEY")
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        resp = client.embeddings.create(model=_OPENAI_MODEL, input=text)
        return resp.data[0].embedding
    except Exception as exc:
        raise EmbedError(f"openai: {exc}") from exc


def _gemini_embed(text: str) -> list[float]:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        try:
            import keyring
            api_key = keyring.get_password("tawn", "gemini") or ""
        except Exception:
            pass
    if not api_key:
        raise EmbedError("no GEMINI_API_KEY")
    try:
        from google import genai
        from google.genai import types as _gtypes
        # text-embedding-004 is a v1 (stable) model — v1beta returns 404
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1"})
        resp = client.models.embed_content(
            model=_GEMINI_MODEL,
            contents=text,
            config=_gtypes.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=_GEMINI_DIMS,
            ),
        )
        return resp.embeddings[0].values
    except Exception as exc:
        raise EmbedError(f"gemini: {exc}") from exc


def _chain():
    """Build embed chain dynamically so unit-test patches on module attributes work.

    Ollama models each get their own entry so the correct model name + dims
    get locked to config on first successful embed.
    """
    import tawn.compiler.embedder as _self
    entries: list[tuple[str, int, object]] = []
    for model_name, dims in _OLLAMA_MODELS:
        # capture model_name in closure
        def _make_ollama_fn(m: str):
            return lambda text: _self._ollama_embed_model(text, m)
        entries.append((model_name, dims, _make_ollama_fn(model_name)))
    entries.append((_OPENAI_MODEL, _OPENAI_DIMS, _self._openai_embed))
    entries.append((_GEMINI_MODEL, _GEMINI_DIMS, _self._gemini_embed))
    return entries


def embed_text(text: str, home: Path) -> list[float]:
    """Embed text using the configured model.

    On first call: auto-detects best available model and locks dims to config.
    On subsequent calls: uses the locked model only.
    Raises EmbedError if no model available or dims mismatch.
    """
    locked_model, locked_dims = get_embed_config(home)
    chain = _chain()

    if locked_model:
        for model_name, dims, fn in chain:
            if model_name == locked_model:
                vec = fn(text)
                if len(vec) != locked_dims:
                    raise EmbedError(
                        f"embed dims mismatch: config says {locked_dims} but "
                        f"{model_name} returned {len(vec)}. "
                        "Run: tawn compile --rebuild"
                    )
                return vec
        raise EmbedError(f"locked model {locked_model!r} not in embed chain")

    # First use: walk fallback chain
    last_err: EmbedError | None = None
    for model_name, dims, fn in chain:
        try:
            vec = fn(text)
        except EmbedError as e:
            last_err = e
            continue
        _write_config(home, {"embed_model": model_name, "embed_dims": dims})
        if len(vec) != dims:
            raise EmbedError(
                f"embed dims mismatch: expected {dims} but got {len(vec)}"
            )
        return vec

    raise EmbedError(NO_EMBED_WARNING + f"\n(last error: {last_err})")
