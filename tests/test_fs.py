import pytest

from tawn.capability.audit import AuditLog
from tawn.capability.fs import GrantError, MediatedFS
from tawn.capability.grants import Grants


@pytest.fixture
def world(tmp_path):
    """A home, a granted read dir, a granted write dir, and forbidden ground."""
    home = tmp_path / "home"
    readable = tmp_path / "readable"
    writable = tmp_path / "writable"
    forbidden = tmp_path / "forbidden"
    for d in (home, readable, writable, forbidden):
        d.mkdir()
    (readable / "a.txt").write_text("readable content")
    (forbidden / "secret.txt").write_text("secret")
    grants = Grants(read=[readable], write=[writable])
    fs = MediatedFS(grants, AuditLog(home / "audit.log"), home=home)
    return fs, home, readable, writable, forbidden


def test_read_granted_path(world):
    fs, home, readable, writable, forbidden = world
    assert fs.read_text(readable / "a.txt") == "readable content"


def test_read_forbidden_path_raises_and_audits(world):
    fs, home, readable, writable, forbidden = world
    with pytest.raises(GrantError):
        fs.read_text(forbidden / "secret.txt")
    denied = [e for e in fs.audit.entries() if not e["ok"]]
    assert denied and denied[0]["op"] == "fs.read"


def test_write_granted_path(world):
    fs, home, readable, writable, forbidden = world
    fs.write_text(writable / "out.md", "note")
    assert (writable / "out.md").read_text() == "note"


def test_write_to_read_only_grant_raises(world):
    fs, home, readable, writable, forbidden = world
    with pytest.raises(GrantError):
        fs.write_text(readable / "nope.md", "x")


def test_home_is_implicitly_writable(world):
    fs, home, readable, writable, forbidden = world
    fs.write_text(home / "raw" / "agent-notes" / "n.md", "self-state")
    assert (home / "raw" / "agent-notes" / "n.md").read_text() == "self-state"


def test_dotdot_escape_is_blocked(world):
    fs, home, readable, writable, forbidden = world
    sneaky = readable / ".." / "forbidden" / "secret.txt"
    with pytest.raises(GrantError):
        fs.read_text(sneaky)


def test_symlink_escape_is_blocked(world):
    fs, home, readable, writable, forbidden = world
    link = readable / "link.txt"
    link.symlink_to(forbidden / "secret.txt")
    with pytest.raises(GrantError):
        fs.read_text(link)


def test_every_allowed_access_is_audited(world):
    fs, home, readable, writable, forbidden = world
    fs.read_text(readable / "a.txt")
    ops = [e["op"] for e in fs.audit.entries() if e["ok"]]
    assert "fs.read" in ops


def test_deny_all_denies_everything(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    outside = tmp_path / "x.txt"
    outside.write_text("x")
    fs = MediatedFS(Grants.deny_all(), AuditLog(home / "audit.log"), home=home)
    with pytest.raises(GrantError):
        fs.read_text(outside)
    with pytest.raises(GrantError):
        fs.write_text(tmp_path / "y.txt", "y")
