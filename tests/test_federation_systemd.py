"""Tests for federation systemd unit generation."""
from pathlib import Path
import pytest
from tawn.federation.systemd import write_units


def test_write_units_creates_files(tmp_path):
    paths = write_units(tawn_bin="/usr/bin/tawn", unit_dir=tmp_path)
    names = {p.name for p in paths}
    assert "tawn-federation.service" in names
    assert "tawn-federation-merge.timer" in names
    assert "tawn-federation-merge.service" in names


def test_watcher_service_content(tmp_path):
    write_units(tawn_bin="/usr/bin/tawn", unit_dir=tmp_path)
    content = (tmp_path / "tawn-federation.service").read_text()
    assert "ExecStart=/usr/bin/tawn" in content
    assert "federation" in content
    assert "Restart=on-failure" in content


def test_merge_timer_content(tmp_path):
    write_units(tawn_bin="/usr/bin/tawn", unit_dir=tmp_path)
    content = (tmp_path / "tawn-federation-merge.timer").read_text()
    assert "OnUnitActiveSec" in content
    assert "timers.target" in content


def test_merge_service_content(tmp_path):
    write_units(tawn_bin="/usr/bin/tawn", unit_dir=tmp_path)
    content = (tmp_path / "tawn-federation-merge.service").read_text()
    assert "federation merge" in content
    assert "/usr/bin/tawn" in content


def test_resource_limits_in_service(tmp_path):
    write_units(tawn_bin="/usr/bin/tawn", unit_dir=tmp_path,
                memory_max_mb=256, cpu_weight=20)
    content = (tmp_path / "tawn-federation.service").read_text()
    assert "MemoryMax=256M" in content
    assert "MemoryHigh=204M" in content
    assert "CPUWeight=20" in content
    assert "MemorySwapMax=0" in content


def test_no_resource_limits_by_default(tmp_path):
    write_units(tawn_bin="/usr/bin/tawn", unit_dir=tmp_path)
    content = (tmp_path / "tawn-federation.service").read_text()
    assert "MemoryMax" not in content
    assert "CPUWeight=50" in content


def test_custom_merge_interval(tmp_path):
    write_units(tawn_bin="/usr/bin/tawn", unit_dir=tmp_path,
                merge_interval_minutes=10)
    content = (tmp_path / "tawn-federation-merge.timer").read_text()
    assert "OnUnitActiveSec=10min" in content
