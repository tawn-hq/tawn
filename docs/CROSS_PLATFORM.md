# Cross-Platform Support — Windows & macOS & Linux

Status of `pip install tawn` on each OS, and what was fixed vs. what
degrades gracefully vs. what's still open.

---

## Audit result (2026-07-23)

Went through every OS-coupled code path in the repo. Summary: the app was
already close — `pathlib` is used consistently, no raw `/`-splits, no
hardcoded shell commands that crash on absence. Two real bugs were found
and fixed; the rest degrade gracefully (systemd features no-op with a
message instead of crashing) rather than needing a redesign.

### Fixed this pass

1. **`db_url` default broke on Windows** (`src/tawn/config.py`) — default
   was `postgresql+psycopg:///tawn` (Unix-socket peer auth). Windows has
   no Unix sockets, so every DB call would fail before the user even saw
   the setup wizard. Now `_default_db_url()` checks `platform.system()`
   and returns a TCP `localhost` URL with `tawn:tawn` credentials on
   Windows, keeping the socket default on Linux/macOS.
2. **Install hints missing a Windows branch** (`src/tawn/dbsetup.py`) —
   `INSTALL_HINTS` only covered apt/dnf/brew. Added a Windows block
   pointing at the postgresql.org installer and `TAWN_DB_URL` override.
3. **PyPI classifiers** — added `Operating System :: Microsoft :: Windows`
   (was Linux + macOS only, purely a listing/discoverability fix).

### Confirmed already fine — no change needed

- **`keyring` cross-platform secret storage.** Checked
  `keyring-25.7.0.dist-info/METADATA`: `SecretStorage` and `jeepney` are
  declared `; sys_platform == "linux"` — pip already skips them on
  Windows/macOS. Windows uses Credential Manager, macOS uses Keychain,
  both built into `keyring` with zero extra deps. The doc used to say this
  needed a `pyproject.toml` extras split; it doesn't.
- **Agent-memory path (`~/.claude/projects/`).** `Path.home()` resolves to
  `%USERPROFILE%` on Windows automatically — Claude Code itself uses the
  same `~/.claude` dotfile convention on every OS (not `%APPDATA%`), so
  `src/tawn/compiler/delta.py::scan_agent_memory()` needs no change.
- **`shutil.which("systemctl")` guards.** Every systemd call site
  (`src/tawn/federation/systemd.py`, `src/tawn/domains/wealth/schedule.py`,
  `src/tawn/cli.py`) already checks for the binary first and returns a
  `(False, "systemctl not found — enable manually")` tuple instead of
  raising. `tawn federation schedule` still writes unit files to
  `~/.config/systemd/user` unconditionally on non-Linux (harmless
  clutter, not a crash) — low-priority cleanup, not a blocker.
- **No raw path-string splitting.** Grepped for `.split('/')` /
  `.split("/")` across `src/tawn/` — none found. Path comparisons already
  go through `pathlib`.
- **Dependencies all ship Windows/macOS wheels.** `psycopg[binary]`,
  `pgvector`, `fastmcp`, `anthropic`, `openai`, `google-genai`, `ollama`,
  `watchfiles`, `rapidfuzz` — no source-only Linux-only packages in the
  dependency tree. `uvicorn` is installed without the `[standard]` extra,
  so there's no `uvloop` requirement (uvloop has no Windows wheels) — this
  was already correct, not a fix.
- **ngrok tunnel, frontend build** — no OS-specific code.

### Still open (background-scheduling only — the app itself works without these)

1. **No macOS `launchd` / Windows Task Scheduler backend.** Wealth
   snapshot timer and federation watcher only automate on Linux via
   systemd; on macOS/Windows the user gets a manual-setup message instead
   of an auto-installed background job. Not a blocker for `pip install
   tawn && tawn serve` — only affects "runs unattended on a schedule."
   Tracked as a follow-up, not required for cross-platform pip install.
2. **`tawn federation schedule` writes systemd units unconditionally** on
   non-Linux instead of skipping — cosmetic, creates an unused directory.

---

## Linux — what's missing for non-Ubuntu distros

- **Arch/Fedora/openSUSE**: `snap` packaging not available; need `rpm` or `PKGBUILD`
- **NixOS**: Nix flake or derivation (community contribution path)
- **AppImage**: self-contained, works on any Linux with glibc 2.17+ — good portable option
- **Peer auth assumption**: some distros (Fedora) disable peer auth by default in `pg_hba.conf`;
  setup wizard should detect connect failure and suggest TCP fallback

---

## Packaging matrix target

| Platform | Install method | Status |
|----------|---------------|--------|
| Linux (Ubuntu 22.04+) | `pip install tawn` | working |
| Linux (Ubuntu) | `snap install tawn` | planned |
| Linux (Debian/Ubuntu) | `apt install tawn` (PPA) | planned |
| macOS 13+ | `brew install tawn` | not started |
| Windows 10/11 | `pip install tawn` | needs fixes above |
| Windows 10/11 | `winget install tawn` | after pip works |

---

## Priority order

1. Path handling (`pathlib` throughout, no raw string splits) — **minimal diff, high impact**
2. Keyring extras split — **one `pyproject.toml` change**
3. PostgreSQL setup wizard Windows defaults — **setup route + docs**
4. Systemd abstraction — **most work, needed for background jobs**
5. Folder-browse dialog — **low priority, web UI workaround exists**
6. Windows daemon / service — **last, most complex**

---

## Testing

For each fix, test matrix entry needs:
- `pytest` run on Windows (GitHub Actions `windows-latest` runner)
- `tawn init && tawn serve` smoke test
- `tawn compile` with a sample `~/.tawn/raw/` note
- Recall via `tawn recall "test"`

Add to CI matrix in `.github/workflows/ci.yml`:
```yaml
os: [ubuntu-latest, windows-latest]
```

Windows job excludes systemd-dependent tests via `pytest -m "not linux_only"`.
