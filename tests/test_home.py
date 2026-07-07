import tawn.home as home_mod


def test_tawn_home_honors_env(tawn_home):
    assert home_mod.tawn_home() == tawn_home


def test_init_home_creates_skeleton(tawn_home):
    home_mod.init_home(tawn_home)
    for rel in home_mod.SKELETON:
        assert (tawn_home / rel).is_dir(), rel


def test_init_home_is_idempotent(tawn_home):
    home_mod.init_home(tawn_home)
    assert home_mod.init_home(tawn_home) == []


def test_init_home_never_deletes(tawn_home):
    home_mod.init_home(tawn_home)
    marker = tawn_home / "raw" / "agent-notes" / "keep.md"
    marker.write_text("keep me")
    home_mod.init_home(tawn_home)
    assert marker.read_text() == "keep me"
