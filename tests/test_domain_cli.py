from typer.testing import CliRunner

from tawn.cli import app

runner = CliRunner()


def test_init_seeds_default_enabled_domains(tawn_home):
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    import yaml

    data = yaml.safe_load((tawn_home / "domains.yaml").read_text())
    assert set(data["enabled"]) == {"wealth", "work", "research", "academic", "hobby"}


def test_domain_list_shows_discovered_and_enabled(tawn_home, monkeypatch):
    import tawn.domains.registry as registry

    runner.invoke(app, ["init"])
    monkeypatch.setattr(
        registry,
        "discovered_entry_point_domains",
        lambda: {"wealth": "tawn", "work": "tawn", "research": "tawn", "academic": "tawn", "hobby": "tawn"},
    )
    result = runner.invoke(app, ["domain", "list"])
    assert result.exit_code == 0
    assert "wealth" in result.output and "enabled" in result.output.lower()


def test_domain_enable_disable_roundtrip(tawn_home):
    runner.invoke(app, ["init"])
    assert runner.invoke(app, ["domain", "disable", "hobby"]).exit_code == 0
    import tawn.domains.registry as registry

    assert "hobby" not in registry.enabled_names(tawn_home)
    assert runner.invoke(app, ["domain", "enable", "hobby"]).exit_code == 0
    assert "hobby" in registry.enabled_names(tawn_home)
