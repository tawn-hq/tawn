# Installing Tawn (Stage 0 — capability spine)

What you get today: the `tawn` CLI, a `~/.tawn/` home, deny-all capability
grants with tamper detection, and an audit log. No memory core yet — that's
Stage 3+. This doc takes you from clone to a verified working install.

## Prerequisites

- Linux (Linux-first per the PRD; anything with Python works for Stage 0)
- Python **3.12+** — check with `python3 --version`
- git

## 1 · Install

```bash
git clone <your-remote-url> taw   # or use your existing checkout
cd taw

python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

`-e` = editable install: code changes take effect without reinstalling.

### Make `tawn` available everywhere (recommended)

The venv install only puts `tawn` on your PATH while the venv is active.
For a global CLI that works from any directory and any shell, use pipx:

```bash
sudo apt install -y pipx        # once (or: brew install pipx)
pipx ensurepath                 # once; restart shell if it changed PATH
pipx install -e /path/to/taw    # editable — repo changes apply immediately
```

Now plain `tawn` works everywhere. The dev venv from step 1 is still what
runs the test suite.

### Alternative — venv only (dev sessions)

```bash
source .venv/bin/activate     # now plain `tawn` works in this shell
```

Without activation, use `.venv/bin/tawn` everywhere you see `tawn` below.

## 2 · Verify the build

```bash
.venv/bin/pytest
```

Expected:

```
============================== 32 passed in ~1s ===============================
```

## 3 · First run

```bash
tawn init
```

Expected output:

```
wrote deny-all /home/<you>/.tawn/grants.yaml
tawn home ready at /home/<you>/.tawn (deny-all; edit grants.yaml, then `tawn grant confirm`)
```

What it created:

```
~/.tawn/
├── raw/agent-notes/     # agents' write-back inbox (Stage 3+)
├── wiki/  vectors/  domains/
├── federation/inbox/  federation/adapters/
├── failures/  handoffs/  personality/
├── grants.yaml          # deny-all capability grants
├── grants.yaml.sha256   # integrity sidecar
└── audit.log            # every grant use, allowed or denied
```

Re-running `tawn init` is safe — it never overwrites an existing
`grants.yaml`.

## 4 · See the capability system working

Check the current surface (fresh install = nothing granted):

```bash
tawn grant list
```

```
read: (none)
write: (none)
observe: (none)
system: off
mcp: (none)
```

Now grant read access to a folder by editing `~/.tawn/grants.yaml`:

```yaml
read: ['~/code']
write: []
observe: []
system: false
mcp: []
```

Run `tawn grant list` again — **it refuses**, because the file changed
without acknowledgment:

```
integrity: grants.yaml was edited since last confirm — review it, then run `tawn grant confirm`
```

That's the tamper detection working. Accept your own edit:

```bash
tawn grant confirm
tawn grant list
```

```
confirmed grants.yaml (66032436bd5e…)
read: /home/<you>/code
write: (none)
...
```

Every one of those operations is now in the audit trail:

```bash
cat ~/.tawn/audit.log
```

```json
{"ts": "...", "op": "init", "target": "/home/<you>/.tawn", "ok": true, "detail": "9 dirs created"}
{"ts": "...", "op": "grant.confirm", "target": ".../grants.yaml", "ok": true, "detail": "6603..."}
```

## 5 · Prove the enforcement (optional, 30 seconds)

The whole point of Stage 0: code physically cannot touch ungrated paths.
Try it from a Python shell:

```bash
.venv/bin/python
```

```python
from tawn.capability.audit import AuditLog
from tawn.capability.fs import MediatedFS, GrantError
from tawn.capability.grants import load_verified
from tawn.home import tawn_home

home = tawn_home()
fs = MediatedFS(load_verified(home / "grants.yaml"), AuditLog(home / "audit.log"), home=home)

fs.read_text("/etc/hostname")     # → GrantError: fs.read denied outside grants
fs.write_text("/tmp/x", "hi")     # → GrantError: fs.write denied outside grants
fs.read_text(home / "grants.yaml")  # works — Tawn's own home is self-granted
```

Both denials land in `~/.tawn/audit.log` with `"ok": false`.

## Database (Stage 1+)

Tawn stores snapshots in Postgres. One command handles setup:

```bash
tawn db setup
```

- Postgres already running → creates the `tawn` database if missing, done.
- No Postgres → prints the exact install commands for your distro; run them, re-run `tawn db setup`.
- Custom setup → `export TAWN_DB_URL=postgresql+psycopg://user@host/dbname`

Health check anytime: `tawn doctor`. Bare `tawn` shows a live status screen.

## Wealth v0 (see it do something real)

```bash
tawn wealth init                 # writes ~/.tawn/domains/wealth/holdings.yaml
$EDITOR ~/.tawn/domains/wealth/holdings.yaml   # NGX + US tickers, usd/land/cash, targets
tawn wealth snapshot             # value + store (--offline = manual prices only)
tawn wealth show                 # dashboard: net worth, allocation vs targets, drift
tawn web                         # web viewer for all domains at http://127.0.0.1:8787
```

Prices: NGX from the exchange's public endpoint, US equities from stooq.com —
both keyless, both fall back to the manual prices in your holdings file when
offline.

### Keep it fresh automatically

```bash
tawn wealth schedule                     # daily snapshots via a systemd user timer
tawn wealth schedule --every hourly      # or any OnCalendar spec
systemctl --user list-timers tawn-wealth-snapshot.timer   # verify
```

Missed runs (machine off) catch up at next boot (`Persistent=true`).

## Models (Stage 2 — ask your twin)

Tawn routes every prompt through its own model router: local Ollama first-class,
cloud (Gemini) optional. No key needed for local.

### Local model (Ollama)

```bash
# 1. install the daemon (once)
curl -fsSL https://ollama.com/install.sh | sh

# 2. choose a model — tawn lists everything that fits this machine's RAM,
#    marks its recommendation, and Enter accepts it. Type a number to pick
#    another, or any ollama tag (e.g. gemma3:270m). -y skips the prompt.
tawn model setup

# 3. talk to it
tawn chat                        # interactive — history carries across turns
tawn ask "summarize what tawn is"   # one-shot
```

Inside `tawn chat`: `exit`/`quit`/ctrl-d leaves, `/new` clears history,
`--sensitive` pins the whole session to the local model. The model you chose
in `tawn model setup` is remembered in `~/.tawn/config.yaml`.

Explore what else your machine could run:

```bash
tawn model explore               # curated picks, sizes, what fits — ★ = recommended
tawn model explore --live        # the full ollama.com directory (236+ models)
tawn model explore --category code
tawn model pull gemma3:4b        # download anything by tag
tawn model list                  # what's installed (+ cloud models your keys unlock)
```

### Cloud models (optional — any key you have)

Tawn enables a cloud provider the moment its key exists. Priority order:

| Provider | Key command | Default model |
|---|---|---|
| Anthropic | `tawn key set anthropic` | claude-opus-4-8 |
| OpenAI | `tawn key set openai` | gpt-5.1 |
| Gemini | `tawn key set gemini` | gemini-2.0-flash |
| DeepSeek | `tawn key set deepseek` | deepseek-chat |

```bash
tawn key set anthropic           # prompted, hidden; stored in the OS keyring, verified
tawn key show anthropic          # "set (keyring)" — never prints the value
tawn chat                        # header shows the active provider chain
```

Failover walks that chain in order and always ends at local Ollama. No keyring
on a headless box? `export ANTHROPIC_API_KEY=...` (or `OPENAI_`/`GEMINI_`/
`DEEPSEEK_`) works as a fallback. Keys never live in files, never in the
ledger, never in error messages.

### Pick the model tawn talks to

```bash
tawn model use                          # numbered picker: cloud + installed local
tawn model use anthropic/claude-haiku-4-5   # or set it directly
tawn model use gemma3:4b                # bare tag = local
tawn model use auto                     # back to the failover chain
```

Inside `tawn chat`, `/model` does the same without leaving the session. The
choice lives in `~/.tawn/config.yaml` (`model:`); the rest of the chain stays
as failover, and `--sensitive` still overrides everything to local.

### One-command onboarding

New machine? Skip all the individual steps:

```bash
tawn setup    # guided: home → database → local model → cloud keys
```

Every step has a sane default (just press Enter) and can be skipped and
re-run later. Safe to run again any time.

### Sensitive prompts stay home

```bash
tawn ask --sensitive "read my ledger and summarize my finances"
```

`--sensitive` structurally removes cloud providers *before* routing — the
prompt cannot leave the machine, even on retry/failover paths.

### The sovereignty ledger

```bash
tawn ledger                      # every model call: provider, tokens, cost, local %
```

Append-only JSONL at `~/.tawn/ledger.jsonl` — metadata only, never prompt text.

If a provider misbehaves (rate limits, 5xx), the router retries once on rate
limits, otherwise fails over in priority order; three straight failures open a
60-second circuit breaker so a dead provider stops eating your time.

## Updating Tawn

Editable installs mean code updates apply instantly:

```bash
git pull                    # that's it for pure code changes (pipx -e and venv -e)
```

After updates that add dependencies or new commands:

```bash
.venv/bin/pip install -e ".[dev]"   # refresh the dev venv
pipx reinstall tawn                  # refresh the global CLI
tawn doctor                          # confirm all green
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `tawn: command not found` | Activate the venv (`source .venv/bin/activate`) or call `.venv/bin/tawn` |
| `integrity: grants.yaml.sha256 missing` | You created grants.yaml by hand — run `tawn grant confirm` |
| `python3.12 required` errors on install | `requires-python = ">=3.12"`; install a newer Python (e.g. `pyenv install 3.12`) |
| Tests touch a weird home | They never touch `~/.tawn` — the suite sets `TAWN_HOME` to a temp dir per test |
| Want a scratch install | `TAWN_HOME=/tmp/tawn-test tawn init` — everything respects the override |

## Uninstall

```bash
rm -rf ~/.tawn          # your data + grants (audit log included — it's yours)
rm -rf <repo>/.venv     # the Python environment
```

## For contributors

See `CONTRIBUTING.md` — conventional commits are enforced by a git hook;
enable it once with `git config core.hooksPath .githooks`.
