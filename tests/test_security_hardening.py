"""Regressions for the four hardening fixes of 2026-07-27.

Each of these encodes a hole that existed and must not reopen.
"""

import yaml
from typer.testing import CliRunner

from tawn.cli import app

runner = CliRunner()


# ── 1. the tunnel is no longer opened for you ────────────────────────────────

def test_the_auto_tunnel_starter_is_gone():
    """`tawn web start` used to publish an unauthenticated API whenever ngrok
    happened to be on PATH."""
    import tawn.cli as cli

    assert not hasattr(cli, "_start_ngrok")


def test_public_is_opt_in_and_still_refuses(tawn_home, monkeypatch):
    """Opting in to a hole is still a hole, so --public explains rather than
    tunnels. This must stay true until authentication exists."""
    started = []
    import tawn.cli as cli

    monkeypatch.setattr(cli, "_port_is_bound", lambda p: True, raising=False)
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *a, **k: started.append(a) or (_ for _ in ()).throw(RuntimeError("stop")),
    )
    result = runner.invoke(app, ["web", "start", "--public"])
    # Whatever happened to the server, no tunnel process was launched.
    assert not any("ngrok" in str(a) for a in started)
    if "refusing to open a public tunnel" in result.stdout:
        assert "no authentication" in result.stdout


# ── 2 & 3. the grants endpoint ───────────────────────────────────────────────

def _client(tawn_home, db_engine):
    from fastapi.testclient import TestClient

    from tawn.web import create_app

    tawn_home.mkdir(parents=True, exist_ok=True)
    return TestClient(create_app(db_engine))


def _write_grants(home, **kw):
    data = {"read": [], "write": [], "observe": [], "system": False,
            "mcp": [], "net": False, "shell": False}
    data.update(kw)
    (home / "grants.yaml").write_text(yaml.safe_dump(data))
    return data


def test_saving_grants_no_longer_erases_net_and_shell(tawn_home, db_engine):
    """The bug: `GrantsBody` never gained the Stage 10 capabilities, so any
    save from Settings silently switched them off."""
    c = _client(tawn_home, db_engine)
    _write_grants(tawn_home, net=True, shell=True)

    c.put("/api/grants", json={"read": ["/tmp"], "net": True, "shell": True})

    saved = yaml.safe_load((tawn_home / "grants.yaml").read_text())
    assert saved["net"] is True
    assert saved["shell"] is True


def test_system_cannot_be_set_over_http(tawn_home, db_engine):
    """`system` is the full-machine-awareness flag. The web surface has no
    authentication, so it must not be reachable from there at all."""
    c = _client(tawn_home, db_engine)
    _write_grants(tawn_home, system=False)

    c.put("/api/grants", json={"read": [], "system": True})

    saved = yaml.safe_load((tawn_home / "grants.yaml").read_text())
    assert saved["system"] is False


def test_an_existing_system_grant_survives_a_web_save(tawn_home, db_engine):
    c = _client(tawn_home, db_engine)
    _write_grants(tawn_home, system=True)

    c.put("/api/grants", json={"read": ["/tmp"]})

    assert yaml.safe_load((tawn_home / "grants.yaml").read_text())["system"] is True


def test_writing_grants_does_not_confirm_them(tawn_home, db_engine):
    """The handler used to call `integrity_confirm` on its own write, so the
    tamper-evidence proved nothing about who made the change."""
    from tawn.capability.integrity import IntegrityError, verify

    c = _client(tawn_home, db_engine)
    _write_grants(tawn_home)
    # Establish a good sidecar first, as `tawn grant confirm` would.
    from tawn.capability.integrity import confirm

    confirm(tawn_home / "grants.yaml")
    verify(tawn_home / "grants.yaml")  # sanity: currently trusted

    body = c.put("/api/grants", json={"read": ["/"]}).json()
    assert body["confirmed"] is False
    assert "tawn grant confirm" in body["message"]

    # The edit is now detectable rather than self-blessed.
    try:
        verify(tawn_home / "grants.yaml")
    except IntegrityError:
        return
    raise AssertionError("the web edit was not detectable — sidecar still matches")


def test_confirming_over_http_is_refused(tawn_home, db_engine):
    """Paired with PUT, a web confirm handed a caller both halves of the
    control. Anyone reaching the port could write grants and bless them."""
    c = _client(tawn_home, db_engine)
    _write_grants(tawn_home)

    body = c.post("/api/grants/confirm").json()
    assert body["ok"] is False
    assert "tawn grant confirm" in body["error"]


# ── 4. attachments do not accumulate forever ─────────────────────────────────

def test_the_sweep_is_actually_wired_into_the_background_loop():
    """It was written, tested and exported — and never called, so every
    document ever attached stayed on disk in full."""
    import inspect

    from tawn._webserver import _start_auto_compiler

    assert "sweep_attachments" in inspect.getsource(_start_auto_compiler)
