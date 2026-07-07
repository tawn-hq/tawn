import pytest

from tawn.capability.integrity import IntegrityError, confirm, sidecar, verify


def _grants(tmp_path, body="read: []\n"):
    f = tmp_path / "grants.yaml"
    f.write_text(body)
    return f


def test_confirm_writes_sidecar(tmp_path):
    f = _grants(tmp_path)
    digest = confirm(f)
    assert sidecar(f).read_text().strip() == digest


def test_verify_passes_after_confirm(tmp_path):
    f = _grants(tmp_path)
    confirm(f)
    verify(f)  # no raise


def test_verify_fails_without_sidecar(tmp_path):
    f = _grants(tmp_path)
    with pytest.raises(IntegrityError):
        verify(f)


def test_verify_fails_after_edit(tmp_path):
    f = _grants(tmp_path)
    confirm(f)
    f.write_text("read: ['~/everything']\n")  # tamper
    with pytest.raises(IntegrityError):
        verify(f)
