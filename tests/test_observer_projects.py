from tawn.capability.grants import Grants
from tawn.observer.config import load_observer_config
from tawn.observer.projects import discover_projects, tier_enabled


def test_every_granted_read_path_becomes_a_project(tmp_path):
    a = tmp_path / "code" / "alpha"
    b = tmp_path / "notes"
    (a / ".git").mkdir(parents=True)
    b.mkdir()
    projects = discover_projects(Grants(read=[a, b]))
    assert {p.name for p in projects} == {"alpha", "notes"}
    assert [p.is_git for p in projects if p.name == "alpha"] == [True]
    assert [p.is_git for p in projects if p.name == "notes"] == [False]


def test_colliding_names_are_disambiguated_by_parent(tmp_path):
    a = tmp_path / "code" / "tawn"
    b = tmp_path / "archive" / "tawn"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    names = {p.name for p in discover_projects(Grants(read=[a, b]))}
    assert names == {"code/tawn", "archive/tawn"}


def test_missing_root_is_skipped(tmp_path):
    assert discover_projects(Grants(read=[tmp_path / "gone"])) == []


def test_tiers_follow_observe_grant():
    g = Grants(observe=["fs", "git"])
    assert tier_enabled(g, "fs") is True
    assert tier_enabled(g, "git") is True
    assert tier_enabled(g, "agents") is False
    assert tier_enabled(Grants(), "fs") is False


def test_config_defaults_and_override(tmp_path):
    cfg = load_observer_config(tmp_path)
    assert cfg.idle_minutes == 20
    assert cfg.correlation_window_seconds == 90
    assert "claude" in cfg.agent_identities

    (tmp_path / "config.yaml").write_text("observer:\n  idle_minutes: 5\n")
    assert load_observer_config(tmp_path).idle_minutes == 5
    # Unspecified keys keep their defaults rather than vanishing.
    assert load_observer_config(tmp_path).burst_files == 4
