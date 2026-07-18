from types import SimpleNamespace

import httpx
import pytest

from tawn.model.providers.ollama import OllamaProvider, recommend_model
from tawn.model.types import ErrorKind, ModelError

GB = 1024**3


def listed(*names_sizes):
    return SimpleNamespace(
        models=[SimpleNamespace(model=n, size=s) for n, s in names_sizes]
    )


def progress(status, completed=None, total=None):
    return SimpleNamespace(status=status, completed=completed, total=total)


class FakeClient:
    def __init__(self, list_result=None, list_exc=None, pull_events=None, pull_exc=None):
        self.list_result = list_result
        self.list_exc = list_exc
        self.pull_events = pull_events or []
        self.pull_exc = pull_exc
        self.pulled: list[str] = []

    def list(self):
        if self.list_exc:
            raise self.list_exc
        return self.list_result

    def pull(self, model, stream=True):
        self.pulled.append(model)
        if self.pull_exc:
            raise self.pull_exc
        yield from self.pull_events


def test_recommend_model_tiers_scale_with_ram():
    assert recommend_model(4 * GB) == "qwen2.5:1.5b"
    assert recommend_model(8 * GB) == "qwen2.5:3b"
    assert recommend_model(16 * GB) == "qwen2.5:7b"
    assert recommend_model(32 * GB) == "qwen2.5:14b"
    assert recommend_model(64 * GB) == "qwen2.5:32b"


def test_has_model_checks_installed_tags():
    client = FakeClient(
        list_result=listed(("qwen2.5:7b", 4 * GB), ("llama3.2:3b", 2 * GB))
    )
    p = OllamaProvider(client=client)
    assert p.has_model("qwen2.5:7b") is True
    assert p.has_model("qwen2.5:14b") is False


def test_installed_models_returns_names_and_sizes():
    client = FakeClient(list_result=listed(("qwen2.5:7b", 4 * GB)))
    models = OllamaProvider(client=client).installed_models()
    assert models == [{"name": "qwen2.5:7b", "size": 4 * GB}]


def test_installed_models_empty_when_daemon_down():
    client = FakeClient(list_exc=httpx.ConnectError("refused"))
    assert OllamaProvider(client=client).installed_models() == []


def test_pull_streams_progress():
    events = [
        progress("pulling manifest"),
        progress("pulling abc", completed=50, total=100),
        progress("success"),
    ]
    client = FakeClient(pull_events=events)
    seen: list[dict] = []
    OllamaProvider(client=client).pull("qwen2.5:7b", on_progress=seen.append)
    assert client.pulled == ["qwen2.5:7b"]
    assert seen[-1]["status"] == "success"
    assert any(s.get("completed") == 50 for s in seen)


def test_pull_daemon_down_raises_model_error():
    client = FakeClient(pull_exc=httpx.ConnectError("refused"))
    with pytest.raises(ModelError) as ei:
        OllamaProvider(client=client).pull("qwen2.5:7b")
    assert ei.value.kind is ErrorKind.SERVER_ERROR
