"""Skill store, sync and import."""

import pytest

from tawn.capability.grants import Grants
from tawn.skills.importer import discover_importable, import_skills
from tawn.skills.store import (
    MARKER, SKILL_FILE, Skill, content_hash, get_skill, list_skills,
    parse_skill, remove_skill, save_skill, slugify,
)
from tawn.skills.sync import detect_targets, sync_out, target_dir

AGENTS = ("CLAUDE_CODE", "CURSOR", "GEMINI_CLI", "CODEX")


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    """Never touch the developer's real ~/.claude while testing."""
    for agent in AGENTS:
        monkeypatch.setenv(f"TAWN_SKILLS_DIR_{agent}", str(tmp_path / "absent" / agent))
    monkeypatch.setenv("TAWN_SKILLS_PLUGIN_GLOB", str(tmp_path / "no-plugins" / "*.md"))


def _skill(name="review", body="Do the review.", **kw):
    return Skill(name=name, description=f"{name} skill", body=body, **kw)


def _agent_dir(tmp_path, monkeypatch, agent="CLAUDE_CODE"):
    d = tmp_path / agent.lower()
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(f"TAWN_SKILLS_DIR_{agent}", str(d))
    return d


def _write_foreign(root, name, body="External skill body.", description="d"):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / SKILL_FILE).write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"
    )
    return d


# ── store ────────────────────────────────────────────────────────────────────

def test_round_trip(tmp_path):
    save_skill(tmp_path, _skill())
    got = get_skill(tmp_path, "review")
    assert got.name == "review"
    assert got.body == "Do the review."
    assert got.description == "review skill"


def test_the_file_format_matches_what_claude_code_uses(tmp_path):
    """A Tawn skill must *be* a Claude Code skill — no conversion step."""
    save_skill(tmp_path, _skill())
    text = (tmp_path / "skills" / "review" / SKILL_FILE).read_text()
    assert text.startswith("---\n")
    assert "name: review" in text
    assert "Do the review." in text
    # And it must parse back with the same reader used on foreign skills.
    assert parse_skill(text).name == "review"


def test_listing_and_removal(tmp_path):
    save_skill(tmp_path, _skill("a"))
    save_skill(tmp_path, _skill("b"))
    assert {s.name for s in list_skills(tmp_path)} == {"a", "b"}
    assert remove_skill(tmp_path, "a") is True
    assert remove_skill(tmp_path, "a") is False
    assert [s.name for s in list_skills(tmp_path)] == ["b"]


def test_an_empty_store_lists_nothing(tmp_path):
    assert list_skills(tmp_path) == []
    assert get_skill(tmp_path, "ghost") is None


def test_provenance_survives_a_round_trip(tmp_path):
    save_skill(tmp_path, _skill(source="imported", imported_from="claude-code"))
    got = get_skill(tmp_path, "review")
    assert got.imported_from == "claude-code"
    assert got.source == "imported"


def test_a_file_without_frontmatter_is_not_a_skill():
    assert parse_skill("just a markdown file") is None
    assert parse_skill("---\n[not: valid: yaml\n---\nbody") is None


def test_names_are_slugified_for_the_filesystem(tmp_path):
    save_skill(tmp_path, _skill("Review My PRs!"))
    assert (tmp_path / "skills" / "review-my-prs").is_dir()
    assert slugify("../../etc") == "etc"


def test_the_hash_covers_the_body_not_the_provenance():
    """A skill synced out and read back must not look like a new skill."""
    a = _skill()
    b = _skill(source="imported", imported_from="claude-code")
    assert content_hash(a) == content_hash(b)
    assert content_hash(a) != content_hash(_skill(body="different"))


# ── sync ─────────────────────────────────────────────────────────────────────

def test_sync_writes_into_a_detected_agent(tmp_path, monkeypatch):
    target = _agent_dir(tmp_path, monkeypatch)
    save_skill(tmp_path, _skill())
    report = sync_out(tmp_path)
    assert report.written == ["claude-code/review"]
    written = target / "review" / SKILL_FILE
    assert written.is_file()
    assert "Do the review." in written.read_text()


def test_sync_marks_what_it_owns(tmp_path, monkeypatch):
    target = _agent_dir(tmp_path, monkeypatch)
    save_skill(tmp_path, _skill())
    sync_out(tmp_path)
    assert (target / "review" / MARKER).exists()


def test_syncing_twice_is_a_noop_not_a_duplicate(tmp_path, monkeypatch):
    target = _agent_dir(tmp_path, monkeypatch)
    save_skill(tmp_path, _skill())
    sync_out(tmp_path)
    sync_out(tmp_path)
    assert [d.name for d in target.iterdir()] == ["review"]


def test_a_hand_written_skill_of_the_same_name_is_never_clobbered(tmp_path, monkeypatch):
    """The worst failure for 'write once, have it everywhere' would be
    destroying what the user wrote themselves."""
    target = _agent_dir(tmp_path, monkeypatch)
    _write_foreign(target, "review", body="MY OWN CAREFULLY WRITTEN SKILL")
    save_skill(tmp_path, _skill())

    report = sync_out(tmp_path)
    assert report.conflicts == ["claude-code/review"]
    assert report.written == []
    assert report.ok is False
    assert "MY OWN CAREFULLY WRITTEN SKILL" in (target / "review" / SKILL_FILE).read_text()


def test_sync_refuses_a_target_outside_the_write_grants(tmp_path, monkeypatch):
    target = _agent_dir(tmp_path, monkeypatch)
    save_skill(tmp_path, _skill())
    report = sync_out(tmp_path, grants=Grants(write=[tmp_path / "elsewhere"]))
    assert report.written == []
    assert any("write:" in s for s in report.skipped)
    assert not (target / "review").exists()


def test_sync_proceeds_when_the_target_is_granted(tmp_path, monkeypatch):
    target = _agent_dir(tmp_path, monkeypatch)
    save_skill(tmp_path, _skill())
    report = sync_out(tmp_path, grants=Grants(write=[target]))
    assert report.written == ["claude-code/review"]


def test_sync_with_no_skills_does_nothing(tmp_path, monkeypatch):
    _agent_dir(tmp_path, monkeypatch)
    assert sync_out(tmp_path).written == []


def test_sync_can_be_limited_to_one_agent(tmp_path, monkeypatch):
    claude = _agent_dir(tmp_path, monkeypatch, "CLAUDE_CODE")
    cursor = _agent_dir(tmp_path, monkeypatch, "CURSOR")
    save_skill(tmp_path, _skill())
    sync_out(tmp_path, agents=["claude-code"])
    assert (claude / "review").exists()
    assert not (cursor / "review").exists()


def test_detect_targets_finds_existing_agents(tmp_path, monkeypatch):
    _agent_dir(tmp_path, monkeypatch)
    names = {a for a, _ in detect_targets()}
    assert "claude-code" in names


def test_target_dir_honours_the_override(tmp_path, monkeypatch):
    monkeypatch.setenv("TAWN_SKILLS_DIR_CLAUDE_CODE", str(tmp_path / "x"))
    assert target_dir("claude-code") == tmp_path / "x"


# ── import ───────────────────────────────────────────────────────────────────

def test_import_finds_skills_in_another_agent(tmp_path, monkeypatch):
    source = _agent_dir(tmp_path, monkeypatch)
    _write_foreign(source, "caveman", body="Talk terse.")
    found = discover_importable()
    assert [s.name for s in found] == ["caveman"]
    assert found[0].imported_from == "claude-code"


def test_import_writes_them_into_the_store(tmp_path, monkeypatch):
    source = _agent_dir(tmp_path, monkeypatch)
    _write_foreign(source, "caveman", body="Talk terse.")
    report = import_skills(tmp_path)
    assert report.imported == ["caveman"]
    stored = get_skill(tmp_path, "caveman")
    assert stored.body == "Talk terse."
    assert stored.imported_from == "claude-code"


def test_a_skill_tawn_synced_out_is_not_imported_back(tmp_path, monkeypatch):
    """Otherwise every sync-then-import cycle forks the skill against itself."""
    _agent_dir(tmp_path, monkeypatch)
    save_skill(tmp_path, _skill())
    sync_out(tmp_path)
    assert discover_importable() == []
    assert import_skills(tmp_path).imported == []


def test_reimporting_the_same_skill_is_a_noop(tmp_path, monkeypatch):
    source = _agent_dir(tmp_path, monkeypatch)
    _write_foreign(source, "caveman", body="Talk terse.")
    assert import_skills(tmp_path).imported == ["caveman"]
    second = import_skills(tmp_path)
    assert second.imported == []
    assert any("already have it" in s for s in second.skipped)


def test_a_name_collision_with_different_content_is_reported_not_merged(tmp_path, monkeypatch):
    source = _agent_dir(tmp_path, monkeypatch)
    save_skill(tmp_path, _skill("caveman", body="MY version"))
    _write_foreign(source, "caveman", body="THEIR version")

    report = import_skills(tmp_path)
    assert report.imported == []
    assert report.conflicts and "caveman" in report.conflicts[0]
    assert get_skill(tmp_path, "caveman").body == "MY version"


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    source = _agent_dir(tmp_path, monkeypatch)
    _write_foreign(source, "caveman")
    report = import_skills(tmp_path, dry_run=True)
    assert report.imported == ["caveman"]
    assert report.dry_run is True
    assert get_skill(tmp_path, "caveman") is None


def test_import_dedupes_the_same_skill_present_in_two_agents(tmp_path, monkeypatch):
    a = _agent_dir(tmp_path, monkeypatch, "CLAUDE_CODE")
    b = _agent_dir(tmp_path, monkeypatch, "CURSOR")
    _write_foreign(a, "shared", body="Same body.")
    _write_foreign(b, "shared", body="Same body.")
    assert len(discover_importable()) == 1


def test_plugin_skills_are_found(tmp_path, monkeypatch):
    plug = tmp_path / "plugins" / "pack" / "skills" / "helper"
    plug.mkdir(parents=True)
    (plug / SKILL_FILE).write_text("---\nname: helper\ndescription: d\n---\n\nHelp.\n")
    monkeypatch.setenv(
        "TAWN_SKILLS_PLUGIN_GLOB",
        str(tmp_path / "plugins" / "*" / "skills" / "*" / SKILL_FILE),
    )
    assert "helper" in {s.name for s in discover_importable()}


def test_nothing_to_import_is_not_an_error(tmp_path, monkeypatch):
    _agent_dir(tmp_path, monkeypatch)
    report = import_skills(tmp_path)
    assert report.imported == []
    assert report.conflicts == []


def test_a_round_trip_through_sync_and_import_is_stable(tmp_path, monkeypatch):
    """Author → sync → import must leave exactly one skill."""
    _agent_dir(tmp_path, monkeypatch)
    save_skill(tmp_path, _skill())
    sync_out(tmp_path)
    import_skills(tmp_path)
    sync_out(tmp_path)
    import_skills(tmp_path)
    assert len(list_skills(tmp_path)) == 1
