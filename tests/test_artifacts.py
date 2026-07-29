"""Durability tests for artifact storage.

A generated artifact cannot be regenerated — the model is nondeterministic, so
a lost diagram is lost, not recomputable. These tests exist to hold that line.
"""

import json

from tawn.artifacts import (
    META_NAME, artifact_dir, content_hash, history, list_artifacts,
    read_artifact, save_artifact, scan, slugify,
)


def _save(home, name="flow", content="graph TD; A-->B", note=""):
    return save_artifact(home, "diagrams", name, content, "mmd", note=note)


# ── append-only versioning ───────────────────────────────────────────────────

def test_a_revision_never_touches_the_earlier_version(tmp_path):
    _save(tmp_path, content="first")
    _save(tmp_path, content="second")
    d = artifact_dir(tmp_path, "diagrams", "flow")
    assert (d / "v001.mmd").read_text() == "first"
    assert (d / "v002.mmd").read_text() == "second"


def test_versions_increment_and_are_all_retained(tmp_path):
    for i in range(5):
        _save(tmp_path, content=f"version {i}")
    art, _, _ = read_artifact(tmp_path, "diagrams", "flow")
    assert [v.number for v in art.versions] == [1, 2, 3, 4, 5]
    assert len(scan(tmp_path, "diagrams", "flow")) == 5


def test_identical_content_does_not_create_a_new_version(tmp_path):
    _, v1, new1 = _save(tmp_path, content="same")
    _, v2, new2 = _save(tmp_path, content="same")
    assert new1 is True and new2 is False
    assert v1.number == v2.number == 1
    assert len(scan(tmp_path, "diagrams", "flow")) == 1


def test_reading_a_specific_old_version(tmp_path):
    _save(tmp_path, content="original")
    _save(tmp_path, content="revised")
    _, v, source = read_artifact(tmp_path, "diagrams", "flow", version=1)
    assert source == "original"
    assert v.number == 1


def test_latest_is_returned_by_default(tmp_path):
    _save(tmp_path, content="original")
    _save(tmp_path, content="revised")
    _, v, source = read_artifact(tmp_path, "diagrams", "flow")
    assert (source, v.number) == ("revised", 2)


# ── the append-only log survives metadata loss ───────────────────────────────

def test_the_index_log_records_every_write(tmp_path):
    _save(tmp_path, content="a")
    _save(tmp_path, content="b")
    _save(tmp_path, name="other", content="c")
    rows = history(tmp_path)
    assert len(rows) == 3
    assert {r["slug"] for r in rows} == {"flow", "other"}
    assert [r["version"] for r in rows if r["slug"] == "flow"] == [1, 2]


def test_content_survives_a_destroyed_meta_json(tmp_path):
    """meta.json is an index, not the record of truth."""
    _save(tmp_path, content="precious work")
    (artifact_dir(tmp_path, "diagrams", "flow") / META_NAME).write_text("{corrupt")

    # The metadata read degrades rather than raising...
    assert read_artifact(tmp_path, "diagrams", "flow") is None
    # ...but nothing was lost: the file and the log both still have it.
    assert scan(tmp_path, "diagrams", "flow") == ["v001.mmd"]
    assert (artifact_dir(tmp_path, "diagrams", "flow") / "v001.mmd").read_text() == (
        "precious work"
    )
    assert history(tmp_path)[0]["hash"] == content_hash("precious work")


def test_a_corrupt_index_line_does_not_hide_the_others(tmp_path):
    _save(tmp_path, content="a")
    path = tmp_path / "artifacts" / "index.jsonl"
    path.write_text(path.read_text() + "{ this is not json\n")
    _save(tmp_path, content="b")
    assert len(history(tmp_path)) == 2


# ── atomic writes ────────────────────────────────────────────────────────────

def test_no_partial_files_are_left_behind(tmp_path):
    _save(tmp_path, content="x")
    leftovers = [
        p.name for p in artifact_dir(tmp_path, "diagrams", "flow").iterdir()
        if p.name.startswith(".tmp-") or p.name.endswith(".part")
    ]
    assert leftovers == []


def test_a_failed_write_leaves_the_previous_version_intact(tmp_path, monkeypatch):
    _save(tmp_path, content="good")
    import tawn.artifacts as mod

    real = mod._atomic_write
    calls = {"n": 0}

    def _flaky(path, text):
        calls["n"] += 1
        if calls["n"] == 1:  # fail on the content write
            raise OSError("disk full")
        return real(path, text)

    monkeypatch.setattr(mod, "_atomic_write", _flaky)
    try:
        _save(tmp_path, content="new")
    except OSError:
        pass

    monkeypatch.setattr(mod, "_atomic_write", real)
    _, v, source = read_artifact(tmp_path, "diagrams", "flow")
    assert source == "good"
    assert v.number == 1


# ── naming ───────────────────────────────────────────────────────────────────

def test_slugify_is_stable_and_filesystem_safe(tmp_path):
    assert slugify("My Diagram: v2!") == "my-diagram-v2"
    assert slugify("") == "untitled"
    assert slugify("../../etc/passwd") == "etc-passwd"


def test_a_traversal_name_cannot_escape_the_artifact_root(tmp_path):
    _save(tmp_path, name="../../escape", content="x")
    root = tmp_path / "artifacts" / "diagrams"
    assert [p.name for p in root.iterdir()] == ["escape"]


def test_two_names_that_slug_alike_share_one_artifact(tmp_path):
    _save(tmp_path, name="Data Flow", content="a")
    _save(tmp_path, name="data-flow", content="b")
    art, _, _ = read_artifact(tmp_path, "diagrams", "data flow")
    assert len(art.versions) == 2


# ── listing ──────────────────────────────────────────────────────────────────

def test_listing_by_kind_and_across_kinds(tmp_path):
    _save(tmp_path, name="one", content="a")
    save_artifact(tmp_path, "briefings", "brief", "text", "md")
    assert [a.name for a in list_artifacts(tmp_path, "diagrams")] == ["one"]
    assert len(list_artifacts(tmp_path)) == 2
    assert list_artifacts(tmp_path / "nowhere") == []


def test_reading_an_absent_artifact_returns_none(tmp_path):
    assert read_artifact(tmp_path, "diagrams", "ghost") is None
    _save(tmp_path, content="a")
    assert read_artifact(tmp_path, "diagrams", "flow", version=99) is None


def test_meta_json_is_valid_json_with_every_version(tmp_path):
    _save(tmp_path, content="a")
    _save(tmp_path, content="b")
    raw = json.loads((artifact_dir(tmp_path, "diagrams", "flow") / META_NAME).read_text())
    assert len(raw["versions"]) == 2
    assert raw["kind"] == "diagrams"
