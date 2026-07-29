# Contributing to Tawn

Rules that keep the history and the codebase consistent. They apply to humans
and agents equally.

## One-time setup

See **[INSTALL.md](INSTALL.md)** for the full development setup — database,
frontend, and the handful of things about this codebase that are not obvious
from reading it. The short version:

```bash
git config core.hooksPath .githooks   # enables the commit-msg check
python3 -m venv .venv && .venv/bin/pip install -e ".[full,dev]"
.venv/bin/tawn db setup
.venv/bin/python -m pytest -q         # expect 1,160 passed
```

## Commit messages — Conventional Commits, enforced

The `.githooks/commit-msg` hook rejects anything that doesn't match:

```
<type>(<scope>)?: <subject>
```

- **type** ∈ `feat fix docs style refactor perf test build ci chore revert`
- **scope** optional, lowercase (`fs`, `grants`, `cli`, `brand`, `plan`)
- **subject**: imperative mood, lowercase start, ≤72 chars, no trailing period
- body (optional): blank line after the subject, explain *why* not *what*

```
feat(fs): resolve symlinks before grant check

A symlink inside a granted dir could point outside it; judging the
resolved target closes the escape.
```

## Branches

- Never commit directly to `main`. Branch per unit of work.
- Names: `feat/<slug>`, `fix/<slug>`, `docs/<slug>` — e.g. `feat/stage-0-capability-spine`.

## Code rules (project-specific, non-negotiable)

- **Every path a user's content comes from or goes to must be grant-checked at
  the point of access.** `capability.grants.path_allowed(grants, path, mode)`
  before reading or writing anything outside `~/.tawn`, and
  `capability_allowed` before offering a tool that needs `net` or `shell`.
  Skipping that check is a review-rejectable defect: it is the gate the whole
  design rests on.

  *This rule previously said all I/O must go through
  `tawn.capability.fs.MediatedFS`. It has not been followed — 6 uses against
  ~135 direct calls — so it is restated above to describe the model the code
  actually implements. Unifying the two is open work; see INSTALL.md §8.*
- **TDD**: failing test first, minimal implementation, test green, then commit.
  One task = one commit (see the active plan in `docs/superpowers/plans/`).
- Tests never touch the real `~/.tawn` — use the `tawn_home` fixture
  (`TAWN_HOME` env override).
- `grants.yaml`, `config.yaml`, `core.db`, `.sha256` sidecars: git-ignored,
  never committed.
- Secrets never in code, config committed to git, or model context — OS
  keyring only. Config files may hold the *names* of environment variables
  (`env_keys`), never their values.
- **Never expose the web API.** It binds `127.0.0.1` and has no authentication.
  Adding anything that tunnels or rebinds it is a security defect until
  Stage 11 lands auth.
- **Prices come from vendor documentation, never memory.** An absent price
  reports honestly as unpriced; a wrong one corrupts the spend dashboard with
  no signal.

## Pull requests

- PR title follows the same conventional format as commits.
- Every PR states which plan task(s) it implements.
- CI-green (pytest) before review.
