"""grants.yaml integrity (design spec §2: "git-ignored, integrity-checked").

SHA-256 sidecar. A hand edit is legal but must be acknowledged with
`tawn grant confirm`; until then Tawn refuses to load the grants.
"""

import hashlib
from pathlib import Path


class IntegrityError(Exception):
    """grants.yaml changed without `tawn grant confirm` (or sidecar missing)."""


def sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def confirm(path: Path) -> str:
    digest = _digest(path)
    sidecar(path).write_text(digest + "\n")
    return digest


def verify(path: Path) -> None:
    side = sidecar(path)
    if not side.exists():
        raise IntegrityError(
            f"{side.name} missing — run `tawn grant confirm` to accept {path.name}"
        )
    if side.read_text().strip() != _digest(path):
        raise IntegrityError(
            f"{path.name} was edited since last confirm — review it, then run `tawn grant confirm`"
        )
