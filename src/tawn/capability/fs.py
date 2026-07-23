"""MediatedFS — the single filesystem chokepoint (design spec §2).

"A write outside write: is impossible by construction, not by good
behaviour." Every component must do file I/O through this class; direct
open() elsewhere in the codebase is a review-rejectable defect.

Resolution first, check second: expanduser().resolve() collapses `..`
and follows symlinks, so a path is judged by where it actually lands.
The Tawn home is implicitly readable+writable (Tawn manages its own
state); everything else needs an explicit grant.
"""

from pathlib import Path

from tawn.capability.audit import AuditLog
from tawn.capability.grants import Grants


class GrantError(PermissionError):
    """Access outside the granted capability surface."""


class MediatedFS:
    def __init__(self, grants: Grants, audit: AuditLog, home: Path):
        self.grants = grants
        self.audit = audit
        self.home = home.expanduser().resolve()

    # -- policy -------------------------------------------------------------

    @staticmethod
    def _under(path: Path, root: Path) -> bool:
        return path == root or root in path.parents

    def _resolve(self, path: Path | str) -> Path:
        return Path(path).expanduser().resolve()

    def _may_read(self, p: Path) -> bool:
        roots = [*self.grants.read, *self.grants.write, self.home]
        return any(self._under(p, r) for r in roots)

    def _may_write(self, p: Path) -> bool:
        roots = [*self.grants.write, self.home]
        return any(self._under(p, r) for r in roots)

    def _gate(self, op: str, p: Path, allowed: bool) -> None:
        self.audit.record(op, str(p), ok=allowed, detail="" if allowed else "no grant")
        if not allowed:
            raise GrantError(f"{op} denied outside grants: {p}")

    # -- operations -----------------------------------------------------------

    def read_text(self, path: Path | str) -> str:
        p = self._resolve(path)
        self._gate("fs.read", p, self._may_read(p))
        return p.read_text()

    def write_text(self, path: Path | str, content: str) -> None:
        p = self._resolve(path)
        self._gate("fs.write", p, self._may_write(p))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def list_dir(self, path: Path | str) -> list[Path]:
        p = self._resolve(path)
        self._gate("fs.list", p, self._may_read(p))
        return sorted(p.iterdir())
