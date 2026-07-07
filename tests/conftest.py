import pytest


@pytest.fixture
def tawn_home(tmp_path, monkeypatch):
    """Isolated Tawn home; no test may touch the real ~/.tawn."""
    home = tmp_path / "tawn-home"
    monkeypatch.setenv("TAWN_HOME", str(home))
    return home
