from tawn.model.catalog import CATALOG, explore

GB = 1024**3


def test_catalog_entries_have_sizes_and_ram_floors():
    assert len(CATALOG) >= 10
    for m in CATALOG:
        assert m.name and ":" in m.name  # ollama tag form
        assert m.download_gb > 0
        assert m.min_ram_gb >= m.download_gb  # needs at least its own weight
        assert m.blurb


def test_explore_marks_fit_and_installed():
    rows = explore(ram_bytes=16 * GB, installed={"qwen2.5:7b"})
    by_name = {r["name"]: r for r in rows}
    assert by_name["qwen2.5:7b"]["fits"] is True
    assert by_name["qwen2.5:7b"]["installed"] is True
    assert by_name["qwen2.5:32b"]["fits"] is False
    assert by_name["qwen2.5:32b"]["installed"] is False


def test_explore_sorted_fitting_first_then_size():
    rows = explore(ram_bytes=16 * GB, installed=set())
    fits = [r["fits"] for r in rows]
    assert fits == sorted(fits, reverse=True)  # fitting models first


def test_explore_includes_recommended_flag():
    rows = explore(ram_bytes=16 * GB, installed=set())
    recommended = [r for r in rows if r["recommended"]]
    assert len(recommended) == 1
    assert recommended[0]["name"] == "qwen2.5:7b"
