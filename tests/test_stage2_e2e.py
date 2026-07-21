"""Stage 2 end-to-end: ask → router → adapter → ledger, all through the CLI."""

from types import SimpleNamespace

from typer.testing import CliRunner

import tawn.model.router as router_mod
from tawn.cli import app
from tawn.model.ledger import Ledger
from tawn.model.providers.ollama import OllamaProvider
from tawn.model.types import ErrorKind, Message, ModelError, ModelResponse, StreamChunk

runner = CliRunner()


class ScriptedProvider:
    def __init__(self, name, locality, text="hello from the twin"):
        self.name = name
        self.locality = locality
        self.model = f"{name}-model"
        self.text = text

    def complete(self, msgs, model=None):
        return ModelResponse(
            text=self.text, model=self.model, provider=self.name,
            tokens_in=7, tokens_out=4,
        )

    def stream_complete(self, msgs, model=None):
        yield StreamChunk(text=self.text)
        yield StreamChunk(text="", done=True, tokens_in=7, tokens_out=4)

    def count_tokens(self, msgs):
        return 1

    def classify_error(self, exc):
        return ErrorKind.UNKNOWN


def test_ask_routes_and_ledgers(tawn_home, monkeypatch):
    local = ScriptedProvider("ollama", "local")
    monkeypatch.setattr(
        router_mod, "default_router",
        lambda home: router_mod.Router([local], Ledger(home / "ledger.jsonl")),
    )
    result = runner.invoke(app, ["ask", "hi"])
    assert result.exit_code == 0
    assert "hello from the twin" in result.output
    (e,) = Ledger(tawn_home / "ledger.jsonl").entries()
    assert e["provider"] == "ollama" and e["ok"] is True


def test_ask_sensitive_never_uses_cloud(tawn_home, monkeypatch):
    cloud = ScriptedProvider("gemini", "cloud", text="CLOUD ANSWER")
    local = ScriptedProvider("ollama", "local", text="local answer")
    monkeypatch.setattr(
        router_mod, "default_router",
        lambda home: router_mod.Router([cloud, local], Ledger(home / "ledger.jsonl")),
    )
    result = runner.invoke(app, ["ask", "--sensitive", "my bank details"])
    assert result.exit_code == 0
    assert "local answer" in result.output
    (e,) = Ledger(tawn_home / "ledger.jsonl").entries()
    assert e["locality"] == "local" and e["sensitive"] is True


def test_ask_streams_and_includes_baseline(tawn_home, monkeypatch):
    tawn_home.mkdir(parents=True, exist_ok=True)
    seen_msgs = []

    class StreamingScriptedProvider(ScriptedProvider):
        def stream_complete(self, msgs, model=None):
            seen_msgs.append(msgs)
            yield StreamChunk(text=self.text)
            yield StreamChunk(text="", done=True, tokens_in=3, tokens_out=2)

    local = StreamingScriptedProvider("ollama", "local")
    monkeypatch.setattr(
        router_mod, "default_router",
        lambda home: router_mod.Router([local], Ledger(home / "ledger.jsonl")),
    )
    result = runner.invoke(app, ["ask", "hi"])
    assert result.exit_code == 0
    assert "hello from the twin" in result.output
    assert seen_msgs[0][0].role == "system"  # baseline prepended


def test_ask_all_down_exits_nonzero(tawn_home, monkeypatch):
    class DownProvider(ScriptedProvider):
        def complete(self, msgs, model=None):
            raise ModelError("down", kind=ErrorKind.SERVER_ERROR, provider=self.name)

        def stream_complete(self, msgs, model=None):
            raise ModelError("down", kind=ErrorKind.SERVER_ERROR, provider=self.name)
            yield  # pragma: no cover — unreachable, keeps this a generator

    monkeypatch.setattr(
        router_mod, "default_router",
        lambda home: router_mod.Router(
            [DownProvider("ollama", "local")], Ledger(home / "ledger.jsonl")
        ),
    )
    result = runner.invoke(app, ["ask", "hi"])
    assert result.exit_code == 1


def test_ledger_command_shows_totals(tawn_home, monkeypatch):
    local = ScriptedProvider("ollama", "local")
    monkeypatch.setattr(
        router_mod, "default_router",
        lambda home: router_mod.Router([local], Ledger(home / "ledger.jsonl")),
    )
    runner.invoke(app, ["ask", "hi"])
    result = runner.invoke(app, ["ledger"])
    assert result.exit_code == 0
    assert "100% local" in result.output


def test_ledger_empty_message(tawn_home):
    result = runner.invoke(app, ["ledger"])
    assert result.exit_code == 0
    assert "ledger empty" in result.output


def test_model_list_daemon_down(tawn_home, monkeypatch):
    monkeypatch.setattr(OllamaProvider, "installed_models", lambda self: [])
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    import tawn.cli as cli_mod  # noqa: F401  (key lookup patched at source)

    import tawn.model.keys as keys_mod

    monkeypatch.setattr(keys_mod.keyring, "get_password", lambda svc, user: None)
    result = runner.invoke(app, ["model", "list"])
    assert result.exit_code == 0
    assert "local: none" in result.output
    assert "no keys set" in result.output


def test_model_explore_offline_uses_catalog(tawn_home, monkeypatch):
    monkeypatch.setattr(OllamaProvider, "installed_models", lambda self: [])
    result = runner.invoke(app, ["model", "explore"])
    assert result.exit_code == 0
    assert "qwen2.5:7b" in result.output
    assert "recommended" in result.output


def _echo_router(home):
    from tawn.model.router import Router

    class Echo(ScriptedProvider):
        def complete(self, msgs, model=None):
            return ModelResponse(
                text=f"echo: {msgs[-1].content} (history {len(msgs)})",
                model=self.model, provider=self.name, tokens_in=1, tokens_out=1,
            )

        def stream_complete(self, msgs, model=None):
            text = f"echo: {msgs[-1].content} (history {len(msgs)})"
            yield StreamChunk(text=text)
            yield StreamChunk(text="", done=True, tokens_in=1, tokens_out=1)

    return Router([Echo("ollama", "local")], Ledger(home / "ledger.jsonl"))


def test_chat_carries_history_and_exits(tawn_home, monkeypatch):
    monkeypatch.setattr(router_mod, "default_router", _echo_router)
    monkeypatch.setattr("tawn.model.personality.profile_is_empty", lambda home: False)
    result = runner.invoke(app, ["chat"], input="hi\nagain\nexit\n")
    assert result.exit_code == 0
    # baseline system msg prepended → system+user = 2 on first turn
    assert "echo: hi (history 2)" in result.output
    # second turn: system+user+assistant+user = 4
    assert "echo: again (history 4)" in result.output


def test_chat_clear_resets_history(tawn_home, monkeypatch):
    monkeypatch.setattr(router_mod, "default_router", _echo_router)
    monkeypatch.setattr("tawn.model.personality.profile_is_empty", lambda home: False)
    result = runner.invoke(app, ["chat"], input="hi\n/new\nfresh\nexit\n")
    assert "history cleared" in result.output
    # after /new, fresh start: system+user = 2
    assert "echo: fresh (history 2)" in result.output


def test_model_setup_pick_by_number_writes_config(tawn_home, monkeypatch):
    pulled: list[str] = []
    monkeypatch.setattr(OllamaProvider, "installed_models", lambda self: [])
    monkeypatch.setattr(OllamaProvider, "has_model", lambda self, m: False)
    monkeypatch.setattr(
        "tawn.cli._pull_with_progress", lambda provider, name: pulled.append(name)
    )
    result = runner.invoke(app, ["model", "setup"], input="1\n")
    assert result.exit_code == 0
    assert len(pulled) == 1
    import yaml

    cfg = yaml.safe_load((tawn_home / "config.yaml").read_text())
    assert cfg["local_model"] == pulled[0]


def test_model_setup_freeform_tag(tawn_home, monkeypatch):
    pulled: list[str] = []
    monkeypatch.setattr(OllamaProvider, "installed_models", lambda self: [])
    monkeypatch.setattr(OllamaProvider, "has_model", lambda self, m: False)
    monkeypatch.setattr(
        "tawn.cli._pull_with_progress", lambda provider, name: pulled.append(name)
    )
    result = runner.invoke(app, ["model", "setup"], input="gemma3:270m\n")
    assert result.exit_code == 0
    assert pulled == ["gemma3:270m"]


def test_model_use_direct_target_writes_config(tawn_home):
    result = runner.invoke(app, ["model", "use", "anthropic/claude-haiku-4-5"])
    assert result.exit_code == 0
    import yaml

    cfg = yaml.safe_load((tawn_home / "config.yaml").read_text())
    assert cfg["model"] == "anthropic/claude-haiku-4-5"


def test_model_use_picker_number(tawn_home, monkeypatch):
    import tawn.model.router as router_mod

    monkeypatch.setattr(router_mod, "get_key", {"anthropic": "sk-a"}.get)
    monkeypatch.setattr(OllamaProvider, "installed_models", lambda self: [])
    result = runner.invoke(app, ["model", "use"], input="1\n")
    assert result.exit_code == 0
    import yaml

    cfg = yaml.safe_load((tawn_home / "config.yaml").read_text())
    assert cfg["model"] == "anthropic/claude-opus-4-8"


def test_model_use_picker_auto(tawn_home, monkeypatch):
    import tawn.model.router as router_mod

    monkeypatch.setattr(router_mod, "get_key", {"anthropic": "sk-a"}.get)
    monkeypatch.setattr(OllamaProvider, "installed_models", lambda self: [])
    result = runner.invoke(app, ["model", "use"], input="0\n")
    assert result.exit_code == 0
    import yaml

    cfg = yaml.safe_load((tawn_home / "config.yaml").read_text())
    assert cfg["model"] == "auto"


def test_chat_model_command_switches(tawn_home, monkeypatch):
    monkeypatch.setattr(router_mod, "default_router", _echo_router)
    monkeypatch.setattr("tawn.model.personality.profile_is_empty", lambda home: False)
    result = runner.invoke(
        app, ["chat"], input="/model gemma3:4b\nhi\nexit\n"
    )
    assert result.exit_code == 0
    assert "model set to gemma3:4b" in result.output
    import yaml

    cfg = yaml.safe_load((tawn_home / "config.yaml").read_text())
    assert cfg["model"] == "gemma3:4b"


def test_setup_wizard_skip_everything(tawn_home, monkeypatch):
    # decline db, model, and keys — wizard must still finish cleanly
    result = runner.invoke(app, ["setup"], input="n\nn\nn\n")
    assert result.exit_code == 0
    assert "tawn home ready" in result.output
    assert "tawn chat" in result.output


def test_default_router_uses_configured_local_model(tawn_home, monkeypatch):
    import tawn.model.keys as keys_mod

    tawn_home.mkdir(parents=True, exist_ok=True)
    (tawn_home / "config.yaml").write_text("local_model: gemma3:4b\n")
    monkeypatch.setattr(keys_mod.keyring, "get_password", lambda svc, user: None)
    for env in ("ANTHROPIC", "OPENAI", "GEMINI", "DEEPSEEK"):
        monkeypatch.delenv(f"{env}_API_KEY", raising=False)
    router = router_mod.default_router(tawn_home)
    (ollama,) = router.providers
    assert ollama.model == "gemma3:4b"
