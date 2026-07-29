"""Loading generated tools into the registry.

Two gates, both required: the tool must be `enabled` (a human reviewed it) and
every capability it declares must be backed by a grant. Either alone would be
insufficient — enabling is consent to the code, and the grant is consent to
what the code may reach.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Callable

from tawn.capability.grants import Grants, capability_allowed
from tawn.model.types import ToolSpec
from tawn.tools.creator import IMPL, list_tools, tool_dir


def _load_run(home: Path, name: str) -> Callable[..., str] | None:
    """Import a generated module and hand back its `run`."""
    path = tool_dir(home, name) / IMPL
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"tawn_tool_{name}", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        # A tool that cannot import is not offered. It stays on disk so the
        # user can look at why.
        return None
    run = getattr(module, "run", None)
    return run if callable(run) else None


def load_tools(
    home: Path, grants: Grants
) -> list[tuple[ToolSpec, Callable[..., str]]]:
    """Enabled generated tools whose capabilities the grants allow."""
    home = Path(home)
    out: list[tuple[ToolSpec, Callable[..., str]]] = []

    for manifest in list_tools(home):
        if not manifest.get("enabled"):
            continue
        name = str(manifest.get("name") or "")
        caps = list(manifest.get("capabilities") or [])
        if not all(capability_allowed(grants, c) for c in caps):
            continue
        run = _load_run(home, name)
        if run is None:
            continue
        out.append(
            (
                ToolSpec(
                    name=name,
                    description=str(manifest.get("description") or ""),
                    parameters=manifest.get("parameters")
                    or {"type": "object", "properties": {}},
                    source=f"local:{name}",
                    capabilities=caps,
                ),
                run,
            )
        )
    return out


def run_tool_test(home: Path, name: str) -> tuple[bool, str]:
    """Run a generated tool's own smoke test."""
    import subprocess
    import sys

    d = tool_dir(Path(home), name)
    test = d / "test_impl.py"
    if not test.is_file():
        return False, "this tool has no generated test"
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(test), "-q"],
            capture_output=True, text=True, timeout=60, cwd=str(d), check=False,
        )
    except Exception as exc:
        return False, f"could not run the test: {exc}"
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-4000:]
