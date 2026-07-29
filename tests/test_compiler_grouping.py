from tawn.compiler.grouping import group_for


def test_history_session_groups_by_file(tmp_path):
    p = str(tmp_path / "history" / "2026-07-22-abc.jsonl")
    key, label = group_for(p, "# Chat Session: fix the router\n\n[user]: hi", tmp_path)
    assert key == p
    assert label == "fix the router"


def test_day_bucketed_import_splits_on_seam(tmp_path):
    p = str(tmp_path / "raw" / "imports" / "generic" / "2026-07-22.md")
    key, label = group_for(p, "# Chat Session: openrouter test\n\n[user]: hi", tmp_path)
    assert key == f"{p}#openrouter test"
    assert label == "openrouter test"


def test_day_bucketed_import_without_seam_falls_back_to_path(tmp_path):
    p = str(tmp_path / "raw" / "imports" / "generic" / "2026-07-22.md")
    key, label = group_for(p, "no seam here", tmp_path)
    assert key == p
    assert label == "2026-07-22"


def test_atomic_memory_file_is_ungrouped(tmp_path):
    p = "/home/u/.claude/projects/proj/memory/never-commit.md"
    key, label = group_for(p, "some fact", tmp_path)
    assert key is None
    assert label is None


def test_repo_document_groups_by_file(tmp_path):
    p = "/home/u/code/proj/README.md"
    key, label = group_for(p, "# Project\n\ntext", tmp_path)
    assert key == p
    assert label == "README.md"


def test_two_seams_in_one_day_file_give_two_keys(tmp_path):
    """The whole point of seam splitting: one day file, many conversations."""
    p = str(tmp_path / "raw" / "imports" / "generic" / "2026-07-22.md")
    k1, _ = group_for(p, "# Chat Session: alpha\n\ntext", tmp_path)
    k2, _ = group_for(p, "# Chat Session: beta\n\ntext", tmp_path)
    assert k1 != k2
