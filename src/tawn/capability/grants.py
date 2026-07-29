"""Capability grants (design spec §2): deny-all until the user grants.

grants.yaml is user-editable, git-ignored, integrity-checked (integrity.py).
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from tawn.capability.integrity import verify

#: Written by `tawn init`. Deny-all: every list empty, system off.
DEFAULT_GRANTS_YAML = """\
# ~/.tawn/grants.yaml — capability grants (deny-all by default)
# Edit, then run `tawn grant confirm` to accept the change.
# Docs: design spec §2. Every grant use is written to audit.log.
read: []      # read-only indexing, e.g. [~/code/projectX, ~/papers]
write: []     # the ONLY writable paths, e.g. [~/Obsidian/Tawn/reviews]
observe: []   # ambient watchers, opt-in each, e.g. [fs, git, agents]
system: false # full-system awareness; per-session opt-in (§6.4)
mcp: []       # enabled MCP servers, e.g. [github, gmail-ro]
net: false    # may tools reach the network (fetch_url, web search)
shell: false  # may tools run shell commands — the widest grant here
"""

#: Capability names a tool may declare. Each maps to a grant in
#: `capability_allowed`; a tool declaring one Tawn cannot check would be a
#: capability with no gate, so the set is closed.
CAPABILITIES = ("read", "write", "net", "shell")


class Grants(BaseModel):
    read: list[Path] = Field(default_factory=list)
    write: list[Path] = Field(default_factory=list)
    observe: list[str] = Field(default_factory=list)
    system: bool = False
    mcp: list[str] = Field(default_factory=list)
    # Booleans rather than path lists: "may it reach the network at all" is the
    # decision worth making, and a URL allowlist users would have to maintain
    # is the kind of control that gets set to `*` on the second frustration.
    net: bool = False
    shell: bool = False

    @classmethod
    def deny_all(cls) -> "Grants":
        return cls()

    @classmethod
    def load(cls, path: Path) -> "Grants":
        if not path.exists():
            return cls.deny_all()
        data = yaml.safe_load(path.read_text()) or {}
        grants = cls.model_validate(data)
        grants.read = [Path(p).expanduser().resolve() for p in grants.read]
        grants.write = [Path(p).expanduser().resolve() for p in grants.write]
        return grants


def capability_allowed(grants: "Grants", capability: str) -> bool:
    """Whether a declared tool capability is backed by a grant.

    `read` and `write` are satisfied by having *any* granted path — the
    per-path check happens at call time in the tool itself, since which path a
    tool touches is only known then.
    """
    if capability == "read":
        return bool(grants.read)
    if capability == "write":
        return bool(grants.write)
    if capability == "net":
        return grants.net
    if capability == "shell":
        return grants.shell
    # An unrecognised capability has no gate, so it is never allowed.
    return False


def path_allowed(grants: "Grants", path: Path, mode: str = "read") -> bool:
    """Whether a concrete path is inside a granted root.

    Built-in file tools call this before every access. Without it a built-in
    tool would be a way around the grant model rather than an expression of it.
    """
    roots = grants.write if mode == "write" else [*grants.read, *grants.write]
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(Path(root).expanduser().resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


def load_verified(path: Path) -> "Grants":
    """The only sanctioned way to obtain grants: integrity check, then load."""
    if not path.exists():
        return Grants.deny_all()
    verify(path)
    return Grants.load(path)
