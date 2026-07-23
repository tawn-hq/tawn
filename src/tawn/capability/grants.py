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
observe: []   # ambient watchers, opt-in each, e.g. [vscode, git]
system: false # full-system awareness; per-session opt-in (§6.4)
mcp: []       # enabled MCP servers, e.g. [github, gmail-ro]
"""


class Grants(BaseModel):
    read: list[Path] = Field(default_factory=list)
    write: list[Path] = Field(default_factory=list)
    observe: list[str] = Field(default_factory=list)
    system: bool = False
    mcp: list[str] = Field(default_factory=list)

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


def load_verified(path: Path) -> "Grants":
    """The only sanctioned way to obtain grants: integrity check, then load."""
    if not path.exists():
        return Grants.deny_all()
    verify(path)
    return Grants.load(path)
