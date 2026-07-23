# Contributing to Tawn

Rules that keep the history and the codebase consistent. They apply to humans
and agents equally.

## One-time setup

```bash
git config core.hooksPath .githooks   # enables the commit-msg check
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
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

- **All filesystem I/O goes through `tawn.capability.fs.MediatedFS`.** A bare
  `open()` / `Path.read_text()` / `Path.write_text()` outside that module (and
  outside tests) is a review-rejectable defect — it bypasses the capability
  gate the whole design rests on.
- **TDD**: failing test first, minimal implementation, test green, then commit.
  One task = one commit (see the active plan in `docs/superpowers/plans/`).
- Tests never touch the real `~/.tawn` — use the `tawn_home` fixture
  (`TAWN_HOME` env override).
- `grants.yaml`, `config.yaml`, `core.db`, `.sha256` sidecars: git-ignored,
  never committed.
- Secrets never in code, config committed to git, or model context — OS
  keyring only.

## Pull requests

- PR title follows the same conventional format as commits.
- Every PR states which plan task(s) it implements.
- CI-green (pytest) before review.
