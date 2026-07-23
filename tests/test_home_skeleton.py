import os
from pathlib import Path
import pytest
from tawn.home import init_home, tawn_home


def test_skeleton_has_memory_dirs(tmp_path):
    home = tmp_path / "tawn"
    home.mkdir()
    init_home(home)
    for rel in [
        "raw/identity", "raw/vault", "raw/agent-notes",
        "raw/review-queue", "wiki", "wiki/.staging",
    ]:
        assert (home / rel).is_dir(), f"missing {rel}"


def test_mcp_servers_yaml_created(tmp_path):
    home = tmp_path / "tawn"
    home.mkdir()
    init_home(home)
    stub = home / "mcp_servers.yaml"
    assert stub.exists()
    assert "servers: {}" in stub.read_text()
