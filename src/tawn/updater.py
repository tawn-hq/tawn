"""Self-update logic for Tawn.

Detects install method, fetches latest release, reinstalls in background.
Daily update timer schedules an EOD reinstall.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TypedDict


class UpdateStatus(TypedDict):
    method: str          # clone | pipx | pip | unknown
    current: str
    latest: str | None
    update_available: bool
    last_check: float | None
    last_update: float | None
    running: bool
    error: str | None


_state: dict = {
    "running": False,
    "last_check": None,
    "last_update": None,
    "latest": None,
    "error": None,
}

_lock = threading.Lock()


def detect_method() -> str:
    tawn_pkg = Path(__file__).parent
    # Running from a git clone: look for .git two dirs up (src/tawn → src → repo_root)
    for parent in (tawn_pkg.parent, tawn_pkg.parent.parent):
        if (parent / ".git").is_dir():
            return "clone"
    # pipx puts things under ~/.local/pipx/venvs/
    if "pipx" in sys.executable or "pipx" in str(tawn_pkg):
        return "pipx"
    if "site-packages" in str(tawn_pkg):
        return "pip"
    return "unknown"


def _pypi_latest() -> str | None:
    import urllib.request
    try:
        with urllib.request.urlopen("https://pypi.org/pypi/tawn/json", timeout=8) as r:
            data = json.loads(r.read())
        return data["info"]["version"]
    except Exception:
        return None


def _github_latest() -> str | None:
    import urllib.request
    try:
        with urllib.request.urlopen(
            "https://api.github.com/repos/tawn-hq/tawn/releases/latest", timeout=8
        ) as r:
            data = json.loads(r.read())
        tag = data.get("tag_name", "")
        return tag.lstrip("v") if tag else None
    except Exception:
        return None


def check_latest() -> str | None:
    latest = _pypi_latest() or _github_latest()
    with _lock:
        _state["latest"] = latest
        _state["last_check"] = time.time()
    return latest


def _run_reinstall_clone(repo_root: Path) -> None:
    subprocess.run(["git", "-C", str(repo_root), "pull", "--ff-only"], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(repo_root)], check=True)


def _run_reinstall_pipx() -> None:
    subprocess.run(["pipx", "upgrade", "tawn"], check=True)


def _run_reinstall_pip() -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "tawn"], check=True)


def _do_update_bg(method: str, repo_root: Path | None) -> None:
    with _lock:
        _state["running"] = True
        _state["error"] = None
    try:
        if method == "clone" and repo_root:
            _run_reinstall_clone(repo_root)
        elif method == "pipx":
            _run_reinstall_pipx()
        else:
            _run_reinstall_pip()
        with _lock:
            _state["last_update"] = time.time()
    except Exception as e:
        with _lock:
            _state["error"] = str(e)
    finally:
        with _lock:
            _state["running"] = False


def trigger_update() -> dict:
    with _lock:
        if _state["running"]:
            return {"ok": False, "error": "update already running"}

    method = detect_method()
    repo_root: Path | None = None
    if method == "clone":
        tawn_pkg = Path(__file__).parent
        for parent in (tawn_pkg.parent, tawn_pkg.parent.parent):
            if (parent / ".git").is_dir():
                repo_root = parent
                break

    t = threading.Thread(target=_do_update_bg, args=(method, repo_root), daemon=True)
    t.start()
    return {"ok": True, "method": method}


def get_status() -> UpdateStatus:
    from tawn import __version__
    method = detect_method()
    with _lock:
        return UpdateStatus(
            method=method,
            current=__version__,
            latest=_state["latest"],
            update_available=bool(_state["latest"] and _state["latest"] != __version__),
            last_check=_state["last_check"],
            last_update=_state["last_update"],
            running=_state["running"],
            error=_state["error"],
        )


def _eod_seconds() -> float:
    """Seconds until 23:55 local time today (or tomorrow if past)."""
    from datetime import datetime, timedelta
    now = datetime.now()
    target = now.replace(hour=23, minute=55, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def start_daily_updater() -> None:
    """Background thread: check + update once daily at ~23:55."""
    def _loop():
        while True:
            wait = _eod_seconds()
            time.sleep(wait)
            try:
                check_latest()
                trigger_update()
            except Exception:
                pass

    t = threading.Thread(target=_loop, daemon=True)
    t.name = "tawn-daily-updater"
    t.start()
