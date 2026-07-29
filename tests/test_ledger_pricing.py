"""Pricing must distinguish "free" from "we have no price for this"."""

from decimal import Decimal

from tawn.model.ledger import PRICES, estimate_cost


def test_known_model_is_priced():
    cost, priced = estimate_cost("gpt-5.1", 1_000_000, 0)
    assert priced is True
    assert cost == Decimal("1.25")


def test_unknown_model_is_flagged_not_silently_zero():
    """Collapsing free and unknown into 0 is what made the ledger understate.

    Six of nine configured providers were absent from PRICES, so a real
    ledger read $0.0021 across 28 calls.
    """
    cost, priced = estimate_cost("some-model-nobody-has-heard-of", 1000, 1000)
    assert cost == Decimal("0")
    assert priced is False


def test_local_model_is_free_and_priced():
    cost, priced = estimate_cost("nomic-embed-text", 1000, 0)
    assert cost == Decimal("0")
    assert priced is True


def test_embedding_model_priced_on_input_only():
    cost, priced = estimate_cost("text-embedding-3-small", 1_000_000, 0)
    assert priced is True
    assert cost == Decimal("0.02")


def test_output_tokens_do_not_bill_on_embeddings():
    cost, _ = estimate_cost("text-embedding-3-small", 0, 1_000_000)
    assert cost == Decimal("0")


def test_every_configured_provider_default_model_has_a_price():
    """Adding a provider without a price must fail here, not report $0.

    The bug was never that seven prices were wrong — it was that forgetting
    a price was invisible.
    """
    from tawn.model.router import CLOUD_REGISTRY

    defaults = {
        "anthropic": "claude-opus-4-8",
        "openai": "gpt-5.1",
        "gemini": "gemini-2.5-flash",
        "deepseek": "deepseek-chat",
        "openrouter": "openai/gpt-4o",
        "kimi": "moonshot-v1-128k",
        "qwen": "qwen-max",
        "groq": "llama-3.3-70b-versatile",
        "grok": "grok-3",
        "mistral": "mistral-large-latest",
    }
    for name, _ in CLOUD_REGISTRY:
        assert name in defaults, f"provider {name!r} has no default model recorded in this test"
        assert defaults[name] in PRICES, f"{name} default {defaults[name]!r} has no price"


def test_embedding_models_are_priced():
    for model in ("text-embedding-3-small", "gemini-embedding-001"):
        _, priced = estimate_cost(model, 1000, 0)
        assert priced is True, f"{model} should be priced"


def test_ollama_tagged_models_are_free_not_unpriced():
    """Ollama names carry a :tag suffix, so an exact-name set never matched.

    `qwen2.5:7b` and `tinyllama:1.1b` read as "no price known" when they are
    in fact local and genuinely free.
    """
    for model in ("qwen2.5:7b", "tinyllama:1.1b", "llama3.2:3b"):
        cost, priced = estimate_cost(model, 1000, 1000)
        assert cost == Decimal("0")
        assert priced is True, f"{model} is local and free"


def test_selectable_gemini_models_are_priced():
    """Coverage follows usage, not just registry defaults.

    1,296 real gemini-2.5-pro calls billed as $0 because only the default
    (flash) was listed.
    """
    for model in ("gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.5-flash"):
        _, priced = estimate_cost(model, 1000, 0)
        assert priced is True, f"{model} should be priced"
