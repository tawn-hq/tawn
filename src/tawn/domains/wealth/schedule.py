"""Background snapshots via a systemd *user* timer.

"The system continually computes prices behind the scenes": a user-level
timer runs `tawn wealth snapshot` on a schedule — no root, no daemon of
our own, survives reboots (Persistent=true catches missed runs).

Written to ~/.config/systemd/user/ with the user's explicit `tawn wealth
schedule` invocation; recorded in audit.log like any state change.
"""

import shutil
import subprocess
from pathlib import Path

UNIT_NAME = "tawn-wealth-snapshot"

SERVICE = """\
[Unit]
Description=tawn wealth snapshot (read-only valuation)

[Service]
Type=oneshot
ExecStart={tawn_bin} wealth snapshot
"""

TIMER = """\
[Unit]
Description=tawn wealth snapshot timer

[Timer]
OnCalendar={on_calendar}
Persistent=true

[Install]
WantedBy=timers.target
"""


def systemd_user_dir() -> Path:
    return Path("~/.config/systemd/user").expanduser()


def write_units(tawn_bin: str, on_calendar: str, unit_dir: Path | None = None) -> list[Path]:
    unit_dir = unit_dir or systemd_user_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    service = unit_dir / f"{UNIT_NAME}.service"
    timer = unit_dir / f"{UNIT_NAME}.timer"
    service.write_text(SERVICE.format(tawn_bin=tawn_bin))
    timer.write_text(TIMER.format(on_calendar=on_calendar))
    return [service, timer]


def enable_timer() -> tuple[bool, str]:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return False, "systemctl not found — enable the timer with your init system"
    for args in (["daemon-reload"], ["enable", "--now", f"{UNIT_NAME}.timer"]):
        proc = subprocess.run(
            [systemctl, "--user", *args], capture_output=True, text=True
        )
        if proc.returncode != 0:
            return False, proc.stderr.strip()
    return True, f"{UNIT_NAME}.timer enabled"
