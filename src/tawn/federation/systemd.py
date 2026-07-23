"""Write and enable systemd user units for the federation watcher + merge timer."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_WATCHER_SERVICE = """\
[Unit]
Description=Tawn federation watcher — ingest AI tool sessions
After=network.target

[Service]
Type=simple
ExecStart={tawn_bin} federation start --foreground
Restart=on-failure
RestartSec=30s
{resource_directives}
[Install]
WantedBy=default.target
"""

_MERGE_SERVICE = """\
[Unit]
Description=Tawn federation merge — process pending records

[Service]
Type=oneshot
ExecStart={tawn_bin} federation merge
{resource_directives}
"""

_MERGE_TIMER = """\
[Unit]
Description=Tawn federation merge timer

[Timer]
OnBootSec=2min
OnUnitActiveSec={interval_minutes}min
Persistent=true

[Install]
WantedBy=timers.target
"""


def _systemd_user_dir() -> Path:
    return Path("~/.config/systemd/user").expanduser()


def _build_resource_directives(memory_max_mb: int | None, cpu_weight: int) -> str:
    """Build systemd [Service] resource control lines from user config."""
    lines: list[str] = []
    if memory_max_mb is not None:
        high = int(memory_max_mb * 0.8)
        lines.append(f"MemoryHigh={high}M")
        lines.append(f"MemoryMax={memory_max_mb}M")
        lines.append("MemorySwapMax=0")       # no swap — stay compact
    lines.append(f"CPUWeight={cpu_weight}")
    lines.append("IOWeight=50")               # don't starve I/O of other processes
    if lines:
        return "\n".join(lines) + "\n"
    return ""


def write_units(
    tawn_bin: str,
    unit_dir: Path | None = None,
    memory_max_mb: int | None = None,
    cpu_weight: int = 50,
    merge_interval_minutes: int = 5,
) -> list[Path]:
    """Write watcher service + merge timer/service. Returns list of written paths."""
    unit_dir = unit_dir or _systemd_user_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)

    resource = _build_resource_directives(memory_max_mb, cpu_weight)
    written: list[Path] = []
    files = {
        "tawn-federation.service": _WATCHER_SERVICE.format(
            tawn_bin=tawn_bin, resource_directives=resource
        ),
        "tawn-federation-merge.service": _MERGE_SERVICE.format(
            tawn_bin=tawn_bin, resource_directives=resource
        ),
        "tawn-federation-merge.timer": _MERGE_TIMER.format(
            interval_minutes=merge_interval_minutes
        ),
    }
    for name, content in files.items():
        p = unit_dir / name
        p.write_text(content)
        written.append(p)
    return written


def enable_units() -> tuple[bool, str]:
    """Run systemctl --user to reload + enable federation service + merge timer."""
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return False, "systemctl not found — enable units manually"
    cmds = [
        ["daemon-reload"],
        ["enable", "--now", "tawn-federation.service"],
        ["enable", "--now", "tawn-federation-merge.timer"],
    ]
    for args in cmds:
        proc = subprocess.run(
            [systemctl, "--user", *args],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return False, proc.stderr.strip() or f"systemctl {' '.join(args)} failed"
    return True, "tawn-federation.service + tawn-federation-merge.timer enabled"


def disable_units() -> tuple[bool, str]:
    """Stop and disable federation units."""
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return False, "systemctl not found"
    for args in [
        ["disable", "--now", "tawn-federation.service"],
        ["disable", "--now", "tawn-federation-merge.timer"],
    ]:
        subprocess.run([systemctl, "--user", *args], capture_output=True)
    return True, "federation units disabled"
