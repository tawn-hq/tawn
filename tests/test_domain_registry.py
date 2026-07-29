from importlib.metadata import EntryPoint

from tawn.domains.base import DomainSpec
import tawn.domains.registry as registry


def fake_entry_points(name="wealth", group="tawn.domains"):
    ep = EntryPoint(name=name, value="tests.fixtures.fake_domain:register", group=group)
    return [ep]


def test_enable_disable_persist_and_audit(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    registry.enable("wealth", tawn_home)
    assert registry.enabled_names(tawn_home) == {"wealth"}
    registry.enable("work", tawn_home)
    assert registry.enabled_names(tawn_home) == {"wealth", "work"}
    registry.disable("wealth", tawn_home)
    assert registry.enabled_names(tawn_home) == {"work"}

    audit = (tawn_home / "audit.jsonl").read_text()
    assert "domain.enable" in audit and "domain.disable" in audit


def test_enabled_names_empty_when_no_file(tawn_home):
    tawn_home.mkdir(parents=True, exist_ok=True)
    assert registry.enabled_names(tawn_home) == set()


def test_enabled_domains_loads_only_enabled_entry_points(tawn_home, monkeypatch):
    tawn_home.mkdir(parents=True, exist_ok=True)
    registry.enable("wealth", tawn_home)

    def fake_register():
        return DomainSpec(name="wealth", label="Wealth")

    monkeypatch.setattr(registry, "discovered_entry_point_domains", lambda: {"wealth": "tawn", "work": "tawn"})
    monkeypatch.setattr(registry, "_load_entry_point", lambda name: fake_register() if name == "wealth" else None)

    specs = registry.enabled_domains(tawn_home)
    assert [s.name for s in specs] == ["wealth"]  # "work" not enabled, never loaded


def test_local_domain_loaded_when_enabled(tawn_home, monkeypatch):
    tawn_home.mkdir(parents=True, exist_ok=True)
    folder = tawn_home / "domains" / "hobby"
    folder.mkdir(parents=True)
    (folder / "domain.py").write_text(
        "from tawn.domains.base import DomainSpec\n"
        "def register():\n"
        "    return DomainSpec(name='hobby', label='Hobby')\n"
    )
    registry.enable("hobby", tawn_home)
    monkeypatch.setattr(registry, "discovered_entry_point_domains", lambda: {})

    specs = registry.enabled_domains(tawn_home)
    assert [s.name for s in specs] == ["hobby"]


def test_broken_local_domain_is_skipped_not_raised(tawn_home, monkeypatch):
    tawn_home.mkdir(parents=True, exist_ok=True)
    folder = tawn_home / "domains" / "broken"
    folder.mkdir(parents=True)
    (folder / "domain.py").write_text("this is not valid python (((\n")
    registry.enable("broken", tawn_home)
    monkeypatch.setattr(registry, "discovered_entry_point_domains", lambda: {})

    specs = registry.enabled_domains(tawn_home)  # must not raise
    assert specs == []


def test_discovered_all_reports_source_and_enabled_flag(tawn_home, monkeypatch):
    tawn_home.mkdir(parents=True, exist_ok=True)
    registry.enable("wealth", tawn_home)
    monkeypatch.setattr(registry, "discovered_entry_point_domains", lambda: {"wealth": "tawn", "work": "tawn"})

    rows = registry.discovered_all(tawn_home)
    by_name = {r["name"]: r for r in rows}
    assert by_name["wealth"] == {"name": "wealth", "source": "tawn", "enabled": True}
    assert by_name["work"] == {"name": "work", "source": "tawn", "enabled": False}
