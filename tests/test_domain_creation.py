from tawn.domains.creation import (
    generate_domain_source,
    has_usable_model,
    write_local_domain,
)

GENERATED = (
    "from tawn.domains.base import DomainSpec\n"
    "def register():\n"
    "    return DomainSpec(name='workouts', label='Workouts')\n"
)


class FakeRouter:
    def __init__(self, text):
        self._text = text

    def complete(self, msgs, sensitive=False):
        from tawn.model.types import ModelResponse

        return ModelResponse(text=self._text, model="fake", provider="fake", tokens_in=1, tokens_out=1)


def test_generate_domain_source_returns_router_text():
    router = FakeRouter(GENERATED)
    source = generate_domain_source("track my workouts", router=router)
    assert "def register()" in source
    assert "DomainSpec" in source


def test_write_local_domain_creates_file(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    path = write_local_domain(tawn_home, "workouts", GENERATED)
    assert path == tawn_home / "domains" / "workouts" / "domain.py"
    assert path.read_text() == GENERATED


def test_has_usable_model_false_when_no_provider(tawn_home, monkeypatch):
    import tawn.model.router as router_mod
    from tawn.model.providers.ollama import OllamaProvider

    monkeypatch.setattr(router_mod, "get_key", lambda provider: None)
    monkeypatch.setattr(OllamaProvider, "installed_models", lambda self: [])
    assert has_usable_model(tawn_home) is False


def test_has_usable_model_true_with_cloud_key(tawn_home, monkeypatch):
    import tawn.model.router as router_mod
    from tawn.model.providers.ollama import OllamaProvider

    monkeypatch.setattr(router_mod, "get_key", lambda provider: "sk-test" if provider == "anthropic" else None)
    monkeypatch.setattr(OllamaProvider, "installed_models", lambda self: [])
    assert has_usable_model(tawn_home) is True
