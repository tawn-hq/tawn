"""Priority router (spec §15.3–15.5).

Providers in list order; the first healthy one wins. `sensitive=True` is
structural: cloud candidates are removed BEFORE selection, so a sensitive
prompt cannot leave the box even through a bug in retry/failover logic.
Every attempt — success or failure — lands in the sovereignty ledger.
"""

import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from tawn.model.breaker import CircuitBreaker
from tawn.model.keys import get_key
from tawn.model.ledger import Ledger, estimate_cost
from tawn.model.types import ErrorKind, Message, ModelError, ModelResponse, Provider

RATE_LIMIT_BACKOFF_S = 2.0


class Router:
    def __init__(
        self,
        providers: list[Provider],
        ledger: Ledger,
        breakers: dict[str, CircuitBreaker] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.providers = providers
        self.ledger = ledger
        self.breakers = breakers if breakers is not None else {
            p.name: CircuitBreaker() for p in providers
        }
        self._sleep = sleep

    def _breaker(self, name: str) -> CircuitBreaker:
        return self.breakers.setdefault(name, CircuitBreaker())

    def _ledger(self, p: Provider, sensitive: bool, resp: ModelResponse | None,
                error: ModelError | None) -> None:
        tokens_in = resp.tokens_in if resp else 0
        tokens_out = resp.tokens_out if resp else 0
        model = resp.model if resp else getattr(p, "model", "")
        self.ledger.record(
            provider=p.name,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=estimate_cost(model, tokens_in, tokens_out),
            locality=p.locality,
            sensitive=sensitive,
            ok=error is None,
            error=error.kind.value if error else "",
        )

    def _attempt(self, p: Provider, msgs: list[Message], sensitive: bool) -> ModelResponse:
        try:
            resp = p.complete(msgs)
        except ModelError as e:
            self._ledger(p, sensitive, None, e)
            self._breaker(p.name).record_failure()
            raise
        self._ledger(p, sensitive, resp, None)
        self._breaker(p.name).record_success()
        return resp

    def complete(self, msgs: list[Message], sensitive: bool = False) -> ModelResponse:
        candidates = [
            p for p in self.providers if not sensitive or p.locality == "local"
        ]
        if not candidates:
            raise ModelError(
                "no eligible provider (sensitive requires a local model — "
                "is ollama installed?)",
                kind=ErrorKind.UNKNOWN,
                provider="router",
            )
        failures: list[ModelError] = []
        for p in candidates:
            if not self._breaker(p.name).allow():
                failures.append(
                    ModelError(
                        f"{p.name}: circuit open (cooling down after repeated failures)",
                        kind=ErrorKind.SERVER_ERROR,
                        provider=p.name,
                    )
                )
                continue
            try:
                return self._attempt(p, msgs, sensitive)
            except ModelError as e:
                failures.append(e)
                if e.kind is ErrorKind.RATE_LIMIT:
                    # transient — one polite retry on the same provider
                    self._sleep(RATE_LIMIT_BACKOFF_S)
                    try:
                        return self._attempt(p, msgs, sensitive)
                    except ModelError as e2:
                        failures.append(e2)
                # any other kind (or failed retry): fall through to next provider
        if failures:
            last = failures[-1]
            # every attempt on the record — one line per provider, nothing swallowed
            detail = "\n  ".join(str(f) for f in failures)
            raise ModelError(
                f"every provider failed:\n  {detail}",
                kind=last.kind,
                provider=last.provider,
            )
        raise ModelError(
            "all providers unavailable (circuit breakers open)",
            kind=ErrorKind.SERVER_ERROR,
            provider="router",
        )


def _make_anthropic(key: str) -> Provider:
    from tawn.model.providers.anthropic import AnthropicProvider

    return AnthropicProvider(api_key=key)


def _make_openai(key: str) -> Provider:
    from tawn.model.providers.openai_compat import openai_provider

    return openai_provider(key)


def _make_gemini(key: str) -> Provider:
    from tawn.model.providers.gemini import GeminiProvider

    return GeminiProvider(api_key=key)


def _make_deepseek(key: str) -> Provider:
    from tawn.model.providers.openai_compat import deepseek_provider

    return deepseek_provider(key)


# priority order — a provider joins the router the moment its key exists
# (`tawn key set <name>` or <NAME>_API_KEY). Ollama is always last: the
# no-key default and the only sensitive-eligible provider.
CLOUD_REGISTRY: list[tuple[str, Callable[[str], Provider]]] = [
    ("anthropic", _make_anthropic),
    ("openai", _make_openai),
    ("gemini", _make_gemini),
    ("deepseek", _make_deepseek),
]


# a few known-good models per cloud provider, for the `tawn model use` picker.
# Free-form "provider/model" is always accepted too.
PROVIDER_MODELS: dict[str, list[str]] = {
    "anthropic": ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"],
    "openai": ["gpt-5.1"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
}


def _read_config(home: Path) -> dict:
    import yaml

    path = Path(home) / "config.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def local_model(home: Path) -> str | None:
    """The local model chosen at `tawn model setup` (~/.tawn/config.yaml)."""
    return _read_config(home).get("local_model")


def model_preference(home: Path) -> str | None:
    """The `model:` preference ("provider/model", "provider", or None=auto)."""
    pref = _read_config(home).get("model")
    return None if pref in (None, "", "auto") else str(pref)


def split_preference(pref: str) -> tuple[str, str | None]:
    """"anthropic/claude-haiku-4-5" → (provider, model); bare provider ok.
    A bare local tag like "gemma3:4b" means ("ollama", that tag)."""
    if "/" in pref:
        provider, model = pref.split("/", 1)
        return provider, model or None
    if ":" in pref:  # ollama tags carry a colon; providers never do
        return "ollama", pref
    return pref, None


def usable_models(home: Path) -> list[dict]:
    """Everything the user can route to right now: keyed cloud providers'
    models + installed local models. Rows: {target, provider, model, locality}."""
    from tawn.model.providers.ollama import OllamaProvider

    rows: list[dict] = []
    for provider_name, _ in CLOUD_REGISTRY:
        if not get_key(provider_name):
            continue
        for m in PROVIDER_MODELS.get(provider_name, []):
            rows.append(
                {
                    "target": f"{provider_name}/{m}",
                    "provider": provider_name,
                    "model": m,
                    "locality": "cloud",
                }
            )
    for m in OllamaProvider().installed_models():
        rows.append(
            {
                "target": f"ollama/{m['name']}",
                "provider": "ollama",
                "model": m["name"],
                "locality": "local",
            }
        )
    return rows


def default_router(home: Path) -> Router:
    """Every cloud provider with a key, in registry order; Ollama always.
    A `model:` preference in config.yaml moves that provider to the front
    (and pins its model) — the rest of the chain stays as failover."""
    from tawn.model.providers.ollama import OllamaProvider

    providers: list[Provider] = []
    for provider_name, factory in CLOUD_REGISTRY:
        key = get_key(provider_name)
        if key:
            providers.append(factory(key))
    chosen = local_model(Path(home))
    providers.append(OllamaProvider(model=chosen) if chosen else OllamaProvider())

    pref = model_preference(Path(home))
    if pref:
        provider_name, model = split_preference(pref)
        for i, p in enumerate(providers):
            if p.name == provider_name:
                if model:
                    p.model = model
                providers.insert(0, providers.pop(i))
                break
    return Router(providers, Ledger(Path(home) / "ledger.jsonl"))
