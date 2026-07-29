import pytest

from tawn.model.breaker import CircuitBreaker
from tawn.model.ledger import Ledger
from tawn.model.router import Router, default_router
from tawn.model.types import ErrorKind, Message, ModelError, ModelResponse, StreamChunk

MSGS = [Message(role="user", content="hello")]


class FakeProvider:
    def __init__(self, name, locality, results=None):
        self.name = name
        self.locality = locality
        self.model = f"{name}-model"
        # each item: ModelResponse to return or ModelError to raise
        self.results = list(results or [])
        self.calls = 0

    def _resp(self, text="ok"):
        return ModelResponse(
            text=text, model=f"{self.name}-model", provider=self.name,
            tokens_in=5, tokens_out=3,
        )

    def complete(self, msgs, model=None):
        self.calls += 1
        if self.results:
            item = self.results.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return self._resp()

    def count_tokens(self, msgs):
        return 1

    def classify_error(self, exc):
        return ErrorKind.UNKNOWN


def err(provider, kind):
    return ModelError(f"{provider}: boom", kind=kind, provider=provider)


def make(tmp_path, *providers, breakers=None, sleep=None):
    return Router(
        list(providers),
        Ledger(tmp_path / "ledger.jsonl"),
        breakers=breakers,
        sleep=sleep or (lambda s: None),
    )


def test_uses_first_provider_and_ledgers(tmp_path):
    cloud = FakeProvider("gemini", "cloud")
    local = FakeProvider("ollama", "local")
    router = make(tmp_path, cloud, local)
    r = router.complete(MSGS)
    assert r.provider == "gemini"
    assert local.calls == 0
    (e,) = Ledger(tmp_path / "ledger.jsonl").entries()
    assert e["provider"] == "gemini" and e["ok"] is True


def test_sensitive_filters_to_local_before_selection(tmp_path):
    cloud = FakeProvider("gemini", "cloud")
    local = FakeProvider("ollama", "local")
    router = make(tmp_path, cloud, local)
    r = router.complete(MSGS, sensitive=True)
    assert r.provider == "ollama"
    assert cloud.calls == 0  # never even attempted
    (e,) = Ledger(tmp_path / "ledger.jsonl").entries()
    assert e["sensitive"] is True and e["locality"] == "local"


def test_sensitive_with_no_local_provider_raises(tmp_path):
    cloud = FakeProvider("gemini", "cloud")
    router = make(tmp_path, cloud)
    with pytest.raises(ModelError):
        router.complete(MSGS, sensitive=True)
    assert cloud.calls == 0


def test_failover_on_quota_exhausted(tmp_path):
    cloud = FakeProvider("gemini", "cloud", [err("gemini", ErrorKind.QUOTA_EXHAUSTED)])
    local = FakeProvider("ollama", "local")
    r = make(tmp_path, cloud, local).complete(MSGS)
    assert r.provider == "ollama"
    entries = Ledger(tmp_path / "ledger.jsonl").entries()
    assert [e["ok"] for e in entries] == [False, True]  # every attempt ledgered


def test_rate_limit_retries_same_provider_once(tmp_path):
    cloud = FakeProvider("gemini", "cloud", [err("gemini", ErrorKind.RATE_LIMIT)])
    local = FakeProvider("ollama", "local")
    slept: list[float] = []
    r = make(tmp_path, cloud, local, sleep=slept.append).complete(MSGS)
    assert r.provider == "gemini"  # second try on same provider won
    assert cloud.calls == 2 and local.calls == 0
    assert len(slept) == 1


def test_breaker_opens_and_skips_provider(tmp_path):
    fails = [err("gemini", ErrorKind.SERVER_ERROR)] * 3
    cloud = FakeProvider("gemini", "cloud", fails)
    local = FakeProvider("ollama", "local")
    breakers = {"gemini": CircuitBreaker(failure_threshold=3)}
    router = make(tmp_path, cloud, local, breakers=breakers)
    for _ in range(3):
        assert router.complete(MSGS).provider in ("gemini", "ollama")
    assert breakers["gemini"].state == "open"
    router.complete(MSGS)
    assert cloud.calls == 3  # open breaker → not attempted again


def test_all_providers_fail_raises_last_error(tmp_path):
    cloud = FakeProvider("gemini", "cloud", [err("gemini", ErrorKind.SERVER_ERROR)])
    local = FakeProvider("ollama", "local", [err("ollama", ErrorKind.SERVER_ERROR)])
    with pytest.raises(ModelError) as ei:
        make(tmp_path, cloud, local).complete(MSGS)
    assert ei.value.provider == "ollama"


def test_default_router_local_only_without_key(tmp_path, monkeypatch):
    import tawn.model.router as router_mod

    monkeypatch.setattr(router_mod, "get_key", lambda provider: None)
    router = default_router(tmp_path)
    assert [p.name for p in router.providers] == ["ollama"]


def test_default_router_enables_every_keyed_provider_in_order(tmp_path, monkeypatch):
    import tawn.model.router as router_mod

    monkeypatch.setattr(router_mod, "get_key", lambda provider: "sk-test")
    router = default_router(tmp_path)
    assert [p.name for p in router.providers] == [
        "anthropic", "openai", "gemini", "deepseek",
        "openrouter", "kimi", "qwen", "groq", "grok", "mistral", "ollama",
    ]


def test_default_router_partial_keys(tmp_path, monkeypatch):
    import tawn.model.router as router_mod

    keys = {"gemini": "sk-g", "deepseek": "sk-d"}
    monkeypatch.setattr(router_mod, "get_key", keys.get)
    router = default_router(tmp_path)
    assert [p.name for p in router.providers] == ["gemini", "deepseek", "ollama"]


def test_split_preference_forms():
    from tawn.model.router import split_preference

    assert split_preference("anthropic/claude-haiku-4-5") == ("anthropic", "claude-haiku-4-5")
    assert split_preference("anthropic") == ("anthropic", None)
    assert split_preference("gemma3:4b") == ("ollama", "gemma3:4b")
    assert split_preference("ollama/gemma3:4b") == ("ollama", "gemma3:4b")


def test_preference_moves_provider_first_and_pins_model(tmp_path, monkeypatch):
    import tawn.model.router as router_mod

    monkeypatch.setattr(router_mod, "get_key", lambda provider: "sk-test")
    (tmp_path / "config.yaml").write_text("model: deepseek/deepseek-reasoner\n")
    router = default_router(tmp_path)
    assert router.providers[0].name == "deepseek"
    assert router.providers[0].model == "deepseek-reasoner"
    # rest of the chain intact as failover
    assert [p.name for p in router.providers[1:]] == [
        "anthropic", "openai", "gemini", "openrouter", "kimi", "qwen", "groq", "grok",
        "mistral", "ollama"
    ]


def test_preference_bare_local_tag(tmp_path, monkeypatch):
    import tawn.model.router as router_mod

    monkeypatch.setattr(router_mod, "get_key", lambda provider: None)
    (tmp_path / "config.yaml").write_text("model: gemma3:4b\n")
    router = default_router(tmp_path)
    assert router.providers[0].name == "ollama"
    assert router.providers[0].model == "gemma3:4b"


def test_preference_auto_is_noop(tmp_path, monkeypatch):
    import tawn.model.router as router_mod

    monkeypatch.setattr(router_mod, "get_key", lambda provider: "sk-test")
    (tmp_path / "config.yaml").write_text("model: auto\n")
    router = default_router(tmp_path)
    assert router.providers[0].name == "anthropic"


def test_usable_models_lists_keyed_cloud_and_installed_local(tmp_path, monkeypatch):
    import tawn.model.router as router_mod
    from tawn.model.providers.ollama import OllamaProvider

    keys = {"anthropic": "sk-a"}
    monkeypatch.setattr(router_mod, "get_key", keys.get)
    monkeypatch.setattr(
        OllamaProvider, "installed_models",
        lambda self: [{"name": "qwen2.5:3b", "size": 1}],
    )
    rows = router_mod.usable_models(tmp_path)
    targets = [r["target"] for r in rows]
    assert "anthropic/claude-opus-4-8" in targets
    assert "ollama/qwen2.5:3b" in targets
    assert not any(t.startswith("openai/") for t in targets)  # no key, no row


def test_stream_yields_chunks_and_ledgers_success(tmp_path):
    class StreamingFakeProvider(FakeProvider):
        def stream_complete(self, msgs, model=None):
            yield StreamChunk(text="hi ")
            yield StreamChunk(text="there")
            yield StreamChunk(text="", done=True, tokens_in=5, tokens_out=3)

    p = StreamingFakeProvider("ollama", "local")
    router = make(tmp_path, p)
    chunks = list(router.stream(MSGS))
    text = "".join(c.text for c in chunks if not c.done)
    assert text == "hi there"
    assert chunks[-1].done and chunks[-1].tokens_in == 5
    (e,) = Ledger(tmp_path / "ledger.jsonl").entries()
    assert e["ok"] is True and e["tokens_in"] == 5


def test_stream_fails_over_before_first_chunk(tmp_path):
    class FailFirstProvider(FakeProvider):
        def stream_complete(self, msgs, model=None):
            raise err(self.name, ErrorKind.SERVER_ERROR)
            yield  # pragma: no cover — unreachable, keeps this a generator

    class OkProvider(FakeProvider):
        def stream_complete(self, msgs, model=None):
            yield StreamChunk(text="ok")
            yield StreamChunk(text="", done=True, tokens_in=1, tokens_out=1)

    cloud = FailFirstProvider("gemini", "cloud")
    local = OkProvider("ollama", "local")
    router = make(tmp_path, cloud, local)
    chunks = list(router.stream(MSGS))
    text = "".join(c.text for c in chunks if not c.done)
    assert text == "ok"  # failed over cleanly, no partial gemini text ever emitted


def test_stream_mid_stream_error_stops_without_splicing(tmp_path):
    class BreaksMidStreamProvider(FakeProvider):
        def stream_complete(self, msgs, model=None):
            yield StreamChunk(text="partial ")
            raise err(self.name, ErrorKind.SERVER_ERROR)

    p = BreaksMidStreamProvider("ollama", "local")
    router = make(tmp_path, p)
    chunks = list(router.stream(MSGS))
    assert "".join(c.text for c in chunks) == "partial "
    assert chunks[-1].done and chunks[-1].error is not None
    (e,) = Ledger(tmp_path / "ledger.jsonl").entries()
    assert e["ok"] is False
