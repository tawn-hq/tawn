import pytest

from tawn.capability.grants import Grants, capability_allowed, path_allowed
from tawn.model.builtins import builtin_tools


def _tools(grants):
    return {spec.name: impl for spec, impl in builtin_tools(grants)}


@pytest.fixture
def granted(tmp_path):
    ro = tmp_path / "ro"
    rw = tmp_path / "rw"
    ro.mkdir()
    rw.mkdir()
    (ro / "a.py").write_text("hello world\nsecond line\n")
    return Grants(read=[ro], write=[rw]), ro, rw


# ── the gate itself ──────────────────────────────────────────────────────────

def test_capability_allowed_maps_each_capability_to_a_grant(tmp_path):
    assert capability_allowed(Grants(read=[tmp_path]), "read") is True
    assert capability_allowed(Grants(), "read") is False
    assert capability_allowed(Grants(net=True), "net") is True
    assert capability_allowed(Grants(shell=True), "shell") is True
    assert capability_allowed(Grants(), "shell") is False
    # An unrecognised capability has no gate, so it must never pass.
    assert capability_allowed(Grants(net=True, shell=True), "telepathy") is False


def test_path_allowed_rejects_outside_and_traversal(granted):
    grants, ro, _ = granted
    assert path_allowed(grants, ro / "a.py", "read") is True
    assert path_allowed(grants, ro / ".." / "elsewhere.txt", "read") is False
    assert path_allowed(grants, ro / "a.py", "write") is False  # ro is read-only


# ── which tools are offered ──────────────────────────────────────────────────

def test_ungrantable_tools_are_not_offered_at_all(granted):
    """Offering a tool whose every call returns 'denied' wastes turns and
    teaches the model that refusals are noise."""
    grants, _, _ = granted
    names = set(_tools(grants))
    assert "read_file" in names and "write_file" in names
    assert "fetch_url" not in names   # net: false
    assert "run_command" not in names  # shell: false


def test_net_and_shell_appear_once_granted(granted):
    grants, _, _ = granted
    grants.net = True
    grants.shell = True
    names = set(_tools(grants))
    assert {"fetch_url", "run_command"} <= names


# ── file tools honour grants per call ────────────────────────────────────────

def test_read_file_reads_a_granted_file(granted):
    grants, ro, _ = granted
    assert "hello world" in _tools(grants)["read_file"](path=str(ro / "a.py"))


def test_read_file_refuses_a_path_outside_every_grant(granted, tmp_path):
    grants, _, _ = granted
    outside = tmp_path / "secret.txt"
    outside.write_text("classified")
    out = _tools(grants)["read_file"](path=str(outside))
    assert out.startswith("denied:")
    assert "classified" not in out


def test_write_file_refuses_a_read_only_path(granted):
    grants, ro, _ = granted
    out = _tools(grants)["write_file"](path=str(ro / "new.txt"), content="x")
    assert out.startswith("denied:")
    assert not (ro / "new.txt").exists()


def test_write_file_writes_under_the_write_grant(granted):
    grants, _, rw = granted
    _tools(grants)["write_file"](path=str(rw / "out.txt"), content="written")
    assert (rw / "out.txt").read_text() == "written"


def test_edit_file_refuses_an_ambiguous_match(granted):
    grants, _, rw = granted
    f = rw / "dup.txt"
    f.write_text("x\nx\n")
    out = _tools(grants)["edit_file"](path=str(f), old="x", new="y")
    assert "2 matches" in out
    assert f.read_text() == "x\nx\n"  # unchanged


def test_edit_file_replaces_a_unique_match(granted):
    grants, _, rw = granted
    f = rw / "u.txt"
    f.write_text("alpha\nbeta\n")
    _tools(grants)["edit_file"](path=str(f), old="beta", new="gamma")
    assert f.read_text() == "alpha\ngamma\n"


def test_edit_file_on_no_match_changes_nothing(granted):
    grants, _, rw = granted
    f = rw / "u.txt"
    f.write_text("alpha\n")
    assert "no match" in _tools(grants)["edit_file"](path=str(f), old="zzz", new="q")
    assert f.read_text() == "alpha\n"


def test_search_files_finds_and_scopes(granted):
    grants, ro, _ = granted
    out = _tools(grants)["search_files"](pattern="second", path=str(ro))
    assert "a.py" in out
    assert "second line" in out


def test_search_files_refuses_an_ungranted_root(granted, tmp_path):
    grants, _, _ = granted
    assert _tools(grants)["search_files"](
        pattern="x", path=str(tmp_path / "nope")
    ).startswith("denied:")


def test_list_dir(granted):
    grants, ro, _ = granted
    assert "a.py" in _tools(grants)["list_dir"](path=str(ro))


# ── net and shell refuse without their grant ─────────────────────────────────

def test_shell_refuses_without_the_grant(granted):
    """Even when reachable, the tool must check — the offer list is a
    convenience, not the security boundary."""
    grants, _, _ = granted
    grants.shell = True
    run = _tools(grants)["run_command"]
    grants.shell = False  # revoked between build and call
    assert run(command="echo hi").startswith("denied:")


def test_shell_runs_when_granted(granted):
    grants, _, _ = granted
    grants.shell = True
    out = _tools(grants)["run_command"](command="echo hi")
    assert "exit 0" in out and "hi" in out


def test_shell_refuses_an_ungranted_cwd(granted, tmp_path):
    grants, _, _ = granted
    grants.shell = True
    assert _tools(grants)["run_command"](
        command="ls", cwd=str(tmp_path / "elsewhere")
    ).startswith("denied:")


def test_fetch_url_refuses_without_the_net_grant(granted):
    grants, _, _ = granted
    grants.net = True
    fetch = _tools(grants)["fetch_url"]
    grants.net = False
    assert fetch(url="https://example.com").startswith("denied:")
