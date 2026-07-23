from pathlib import Path

import pytest

from tawn.capability.grants import DEFAULT_GRANTS_YAML, Grants, load_verified
from tawn.capability.integrity import IntegrityError, confirm


def test_deny_all_grants_nothing():
    g = Grants.deny_all()
    assert g.read == [] and g.write == [] and g.observe == []
    assert g.system is False and g.mcp == []


def test_missing_file_loads_as_deny_all(tmp_path):
    g = Grants.load(tmp_path / "grants.yaml")
    assert g == Grants.deny_all()


def test_load_expands_and_resolves_paths(tmp_path):
    f = tmp_path / "grants.yaml"
    f.write_text("read: ['~/code/projectX']\nwrite: []\n")
    g = Grants.load(f)
    assert g.read == [Path("~/code/projectX").expanduser().resolve()]


def test_default_template_is_deny_all(tmp_path):
    f = tmp_path / "grants.yaml"
    f.write_text(DEFAULT_GRANTS_YAML)
    assert Grants.load(f) == Grants.deny_all()


def test_load_verified_missing_file_is_deny_all(tmp_path):
    assert load_verified(tmp_path / "grants.yaml") == Grants.deny_all()


def test_load_verified_rejects_unconfirmed_file(tmp_path):
    f = tmp_path / "grants.yaml"
    f.write_text("read: ['~/code']\n")
    with pytest.raises(IntegrityError):
        load_verified(f)


def test_load_verified_accepts_confirmed_file(tmp_path):
    f = tmp_path / "grants.yaml"
    f.write_text("read: ['~/code']\n")
    confirm(f)
    g = load_verified(f)
    assert g.read and g.read[0].name == "code"
