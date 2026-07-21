from tawn.model.identity import baseline_system_prompt, with_baseline
from tawn.model.types import Message


def test_baseline_mentions_capability_model_and_ledger(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    prompt = baseline_system_prompt(tawn_home)
    assert "deny-all" in prompt.lower() or "capability" in prompt.lower()
    assert "sensitive" in prompt.lower()


def test_baseline_lists_enabled_domains(tawn_home, monkeypatch):
    import tawn.model.identity as identity_mod

    monkeypatch.setattr(
        identity_mod, "enabled_domains", lambda home: [
            type("D", (), {"name": "wealth", "label": "Wealth"})(),
            type("D", (), {"name": "work", "label": "Work"})(),
        ]
    )
    prompt = baseline_system_prompt(tawn_home)
    assert "wealth" in prompt.lower() and "work" in prompt.lower()


def test_with_baseline_prepends_exactly_one_system_message(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    msgs = [Message(role="user", content="hi")]
    result = with_baseline(msgs, tawn_home)
    assert len(result) == 2
    assert result[0].role == "system"
    assert result[1] == msgs[0]
