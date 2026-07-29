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

# Stand-in for blank chunk text; see embed_texts().
_EMPTY_PLACEHOLDER = "(empty)"


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


# SDK clients are cached per process.
#
# Constructing one costs a TLS handshake plus API discovery. Building a fresh
# client per embedding made that a per-chunk cost: measured at 43s for the
# first call versus 0.8-1.9s on a reused client — roughly 42 seconds of pure
# setup, repeated for every chunk in the corpus. Reuse is not an optimisation
# here, it is the difference between hours and days.
_CLIENTS: dict[str, object] = {}


def _openai_client():
    if "openai" not in _CLIENTS:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            try:
                import keyring
                api_key = keyring.get_password("tawn", "openai") or ""
            except Exception:
                pass
        if not api_key:
            raise EmbedError("no OPENAI_API_KEY")
        import openai
        _CLIENTS["openai"] = openai.OpenAI(api_key=api_key, timeout=60.0)
    return _CLIENTS["openai"]


def _gemini_client():
    if "gemini" not in _CLIENTS:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            try:
                import keyring
                api_key = keyring.get_password("tawn", "gemini") or ""
            except Exception:
                pass
        if not api_key:
            raise EmbedError("no GEMINI_API_KEY")
        from google import genai
        # Explicit timeout: an unbounded default leaves a stalled TCP
        # connection hanging forever instead of raising EmbedError, which is
        # what the compiler's retry/backoff loop needs to see to move on.
        _CLIENTS["gemini"] = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1", "timeout": 60_000},
        )
    return _CLIENTS["gemini"]


def _openai_embed(text: str) -> list[float]:
    try:
        resp = _openai_client().embeddings.create(model=_OPENAI_MODEL, input=text)
        return resp.data[0].embedding
    except EmbedError:
        raise
    except Exception as exc:
        raise EmbedError(f"openai: {exc}") from exc


def _gemini_embed(text: str) -> list[float]:
    try:
        from google.genai import types as _gtypes
        resp = _gemini_client().models.embed_content(
            model=_GEMINI_MODEL,
            contents=text,
            config=_gtypes.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=_GEMINI_DIMS,
            ),
        )
        return resp.embeddings[0].values
    except EmbedError:
        raise
    except Exception as exc:
        raise EmbedError(f"gemini: {exc}") from exc


def _gemini_embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed many texts in one Gemini call."""
    try:
        from google.genai import types as _gtypes
        resp = _gemini_client().models.embed_content(
            model=_GEMINI_MODEL,
            contents=texts,
            config=_gtypes.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=_GEMINI_DIMS,
            ),
        )
        vectors = [list(e.values) for e in resp.embeddings]
    except EmbedError:
        raise
    except Exception as exc:
        raise EmbedError(f"gemini batch: {exc}") from exc
    if len(vectors) != len(texts):
        raise EmbedError(
            f"gemini batch returned {len(vectors)} vectors for {len(texts)} inputs"
        )
    return vectors


def _ollama_embed_batch(texts: list[str], model: str) -> list[list[float]]:
    """Embed many texts in one Ollama call.

    The per-text `embeddings()` endpoint costs a full round trip each; the
    newer `embed()` endpoint takes a list and amortises that. Measured ~2x
    at batch size 8 on nomic-embed-text.
    """
    try:
        import ollama as ollama_sdk
        resp = ollama_sdk.embed(model=model, input=texts)
        vectors = resp["embeddings"]
    except Exception as exc:
        raise EmbedError(f"ollama/{model} batch: {exc}") from exc
    if len(vectors) != len(texts):
        raise EmbedError(
            f"ollama/{model} batch returned {len(vectors)} vectors for {len(texts)} inputs"
        )
    return [list(v) for v in vectors]


def _openai_embed_batch(texts: list[str]) -> list[list[float]]:
    try:
        resp = _openai_client().embeddings.create(model=_OPENAI_MODEL, input=texts)
    except Exception as exc:
        raise EmbedError(f"openai batch: {exc}") from exc
    # The API does not guarantee ordering; `index` does.
    ordered = sorted(resp.data, key=lambda d: d.index)
    return [list(d.embedding) for d in ordered]


def _batch_fn_for(model_name: str):
    """Return a batch embed callable for `model_name`, or None if unsupported."""
    if any(model_name == m for m, _ in _OLLAMA_MODELS):
        return lambda texts: _ollama_embed_batch(texts, model_name)
    if model_name == _OPENAI_MODEL:
        return _openai_embed_batch
    if model_name == _GEMINI_MODEL:
        return _gemini_embed_batch
    return None


_LOCAL_MODEL_NAMES = frozenset(m for m, _ in _OLLAMA_MODELS)


def _provider_for(model: str) -> tuple[str, str]:
    """(provider, locality) for a model name."""
    if model in _LOCAL_MODEL_NAMES:
        return "ollama", "local"
    if model == _GEMINI_MODEL:
        return "gemini", "cloud"
    return "openai", "cloud"


def _record_embed(
    home: Path,
    model: str,
    texts: list[str],
    elapsed_ms: float,
    batch_id: str,
) -> None:
    """Write one ledger entry per text.

    Per text rather than per batch so cost stays attributable to a chunk;
    `batch_id` records which texts shared one provider round trip, and the
    batch's elapsed time is split by input length so a long chunk carries
    more of it than a short one.

    Local embeds cost nothing and are still recorded: call count and elapsed
    time are what explain a slow compile, and a ledger that omits free calls
    cannot answer that.
    """
    from tawn.model.ledger import Ledger, estimate_cost

    led = Ledger(home / "ledger.jsonl")
    provider, locality = _provider_for(model)
    total_chars = sum(len(t) for t in texts) or 1

    for text in texts:
        # Embedding APIs do not return usage; ~4 chars per token.
        tokens = max(1, len(text) // 4)
        cost, priced = estimate_cost(model, tokens, 0)
        led.record(
            provider=provider,
            model=model,
            tokens_in=tokens,
            tokens_out=0,
            cost_usd=cost,
            locality=locality,
            sensitive=False,
            ok=True,
            caller="system",
            operation="embed",
            domain=None,
            batch_id=batch_id,
            elapsed_ms=int(elapsed_ms * len(text) / total_chars),
            priced=priced,
        )


def _safe_record(home: Path, model: str, texts: list[str], elapsed_ms: float, batch_id: str) -> None:
    """Ledger writes are best-effort — never fail an embed over bookkeeping."""
    import tawn.compiler.embedder as _self

    try:
        _self._record_embed(home, model, texts, elapsed_ms, batch_id)
    except Exception:  # noqa: BLE001 — see docstring
        pass


def embed_texts(
    texts: list[str],
    home: Path,
    batch_size: int = 32,
) -> tuple[list[list[float]], str, int]:
    """Embed many texts, batching where the provider supports it.

    Returns (vectors, model_name, dims) with one vector per input, in order.
    Falls back to per-text calls for providers without a batch endpoint, and
    for any batch that fails — a provider hiccup should cost throughput, not
    correctness.
    """
    if not texts:
        return [], "", 0

    # Providers reject empty inputs, and they reject the *whole batch* for it:
    # Gemini answers `EmbedContentRequest.content contains an empty Part`. One
    # blank chunk out of 12,298 was enough to fail every batch it landed in and
    # abort an 8,586-chunk run. Substituting a placeholder keeps one bad row
    # from poisoning its neighbours — the resulting vector is meaningless, but
    # so is the chunk, and callers drop empty chunks anyway.
    texts = [t if (t and t.strip()) else _EMPTY_PLACEHOLDER for t in texts]

    # Establish which model is in play (and lock config on first use) with a
    # single call, so the batch path never has to guess.
    import time as _time
    import uuid as _uuid

    _t0 = _time.time()
    first_vec, model_name, dims = embed_text_with_meta(texts[0], home)
    _safe_record(home, model_name, [texts[0]], (_time.time() - _t0) * 1000, _uuid.uuid4().hex[:12])
    if len(texts) == 1:
        return [first_vec], model_name, dims

    out: list[list[float]] = [first_vec]
    remaining = texts[1:]
    batch_fn = _batch_fn_for(model_name)

    for start in range(0, len(remaining), batch_size):
        window = remaining[start:start + batch_size]
        batch_id = _uuid.uuid4().hex[:12]
        t0 = _time.time()
        if batch_fn is not None:
            try:
                out.extend(batch_fn(window))
                _safe_record(home, model_name, window, (_time.time() - t0) * 1000, batch_id)
                continue
            except EmbedError:
                pass  # fall through to per-text
        for text in window:
            vec, _, _ = embed_text_with_meta(text, home)
            out.append(vec)
        _safe_record(home, model_name, window, (_time.time() - t0) * 1000, batch_id)

    return out, model_name, dims


def cloud_embeds_allowed(home: Path | None = None) -> bool:
    """True only when the user has explicitly opted in to cloud embedding.

    Embedding sends the *entire corpus* to whichever provider is selected —
    every note, every imported conversation. That is a different exposure from
    a single chat completion, and it must never happen because a config value
    drifted. It did: `embed_model` was left at an OpenAI model after a settings
    change, and a rebuild shipped the corpus off-machine for 56 minutes before
    anyone noticed.

    Opt in with `embed_allow_cloud: true` in config.yaml, or TAWN_EMBED_ALLOW_CLOUD=1.
    """
    if os.environ.get("TAWN_EMBED_ALLOW_CLOUD", "").strip().lower() in ("1", "true", "yes"):
        return True
    if home is None:
        from tawn.home import tawn_home
        home = tawn_home()
    return bool(_read_config(home).get("embed_allow_cloud", False))


def _chain(home: Path | None = None):
    """Build embed chain dynamically so unit-test patches on module attributes work.

    Ollama models each get their own entry so the correct model name + dims
    get locked to config on first successful embed. Cloud providers are
    appended only when explicitly permitted — see `cloud_embeds_allowed`.
    """
    import tawn.compiler.embedder as _self
    entries: list[tuple[str, int, object]] = []
    for model_name, dims in _OLLAMA_MODELS:
        # capture model_name in closure
        def _make_ollama_fn(m: str):
            return lambda text: _self._ollama_embed_model(text, m)
        entries.append((model_name, dims, _make_ollama_fn(model_name)))
    if _self.cloud_embeds_allowed(home):
        entries.append((_OPENAI_MODEL, _OPENAI_DIMS, _self._openai_embed))
        entries.append((_GEMINI_MODEL, _GEMINI_DIMS, _self._gemini_embed))
    return entries


def embed_text_with_meta(text: str, home: Path) -> tuple[list[float], str, int]:
    """Embed text, reporting which model actually produced the vector.

    Returns (vector, model_name, dims). Callers persist the model and width
    alongside the vector: the storage column is dimensionless, so widths can
    coexist, but distance operators reject mixed-width comparisons — recall
    has to know which rows are comparable, and a re-embed has to know what it
    is replacing.
    """
    used: dict[str, object] = {}
    vec = _embed_text_inner(text, home, used)
    return vec, str(used.get("model", "")), len(vec)


def embed_text(text: str, home: Path) -> list[float]:
    """Embed text using the configured model. See `embed_text_with_meta`."""
    return _embed_text_inner(text, home, {})


def _embed_text_inner(text: str, home: Path, used: dict) -> list[float]:
    """Embed text using the configured model.

    On first call: auto-detects best available model and locks dims to config.
    On subsequent calls: uses the locked model, falling back to any other
    chain entry that produces the SAME dims if the locked one fails — a
    vector column has a fixed width, so a fallback with different dims
    would just fail the insert; only dims-compatible fallbacks are safe.
    Raises EmbedError if no model available or dims mismatch.
    """
    locked_model, locked_dims = get_embed_config(home)
    chain = _chain(home)

    if locked_model:
        last_err: EmbedError | None = None
        locked_fn = None
        fallbacks: list[tuple[str, object]] = []
        for model_name, dims, fn in chain:
            if model_name == locked_model:
                locked_fn = fn
            elif dims == locked_dims:
                fallbacks.append((model_name, fn))
        if locked_fn is None:
            raise EmbedError(f"locked model {locked_model!r} not in embed chain")

        for model_name, fn in [(locked_model, locked_fn)] + fallbacks:
            try:
                vec = fn(text)
            except EmbedError as e:
                last_err = e
                continue
            if len(vec) != locked_dims:
                # The storage column is dimensionless, so this no longer
                # fails the insert — config was simply stale. Record the
                # truth and let the row carry its own provenance; recall
                # filters to the width currently in use.
                _write_config(home, {"embed_model": model_name, "embed_dims": len(vec)})
            used["model"] = model_name
            return vec
        raise EmbedError(f"{locked_model} and all dims-{locked_dims} fallbacks failed (last: {last_err})")

    # First use: walk fallback chain
    last_err: EmbedError | None = None
    for model_name, dims, fn in chain:
        try:
            vec = fn(text)
        except EmbedError as e:
            last_err = e
            continue
        _write_config(home, {"embed_model": model_name, "embed_dims": len(vec)})
        used["model"] = model_name
        return vec

    raise EmbedError(NO_EMBED_WARNING + f"\n(last error: {last_err})")
