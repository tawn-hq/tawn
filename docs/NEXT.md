# What to do after this PR

Written 2026-08-03, after the observer/sweep work. Companion to `ROADMAP.md`
(build stages) and `tawn-hq/docs/OSS-ROADMAP.md` (the open-source journey).

This is the near-term queue only — one PR's worth of work per section, ordered so
that each unblocks the next.

## What the PR itself contains

26 files changed, ~1,670 insertions. Nine new files.

- **Git reconciliation sweep** — `observer/sweep.py`, watermark migration, commit
  and working-tree reconciliation, snapshot scan for non-git projects
- **Transcript attribution** — `observer/transcripts.py`, replacing an mtime
  heuristic that could only work in real time
- **Note fixes** — notes moved to `~/.tawn/reviews/<project>/`, made readable from
  CLI, web and API
- **History robustness** — one corrupt file no longer takes down `/api/history`
- **Watcher correctness** — truthful arming signal, no more silently swallowed
  handler failures, sweep on arm
- **Money** — `Decimal` end to end on the spend routes
- **Review models** — configurable, auto-selected, and every keyed cloud
  provider's live catalogue including OpenRouter
- **UI** — Observer page, nav icons, note viewer, reconcile controls

## Blocked on you, not on code

These cannot be done from inside the repo.

1. **Revoke the leaked GitHub token.** It was in `.git/config` in plaintext for
   weeks and appeared in every `git remote -v`. Stripping it from the remote does
   not un-expose it. https://github.com/settings/tokens
2. **Open the PR.** It is also the first real exercise of
   `.github/workflows/pr-checks.yml`, which has never run on GitHub. Expect to fix
   something in it — a workflow that has never executed is not a working workflow.
3. **`ollama pull qwen2.5:7b`.** qwen3:0.6b writes analysis that invents files.
   The facts in a note are safe because they are rendered from the database, but
   the prose is not usable. The preference list picks the new model up with no
   config change.
4. **Record baseline adoption numbers** — PyPI downloads, stars, dependants. Every
   funding application asks, and there is currently no answer.

## Next PR — durability (`ROADMAP.md` stage 22)

The highest-priority build item, and the only one where waiting risks losing work
that cannot be recreated: ~12,300 chunks and 11,988 entities live in one Postgres
with no backup, and the enrichment pass alone cost ~44 hours.

- `BackupStore` interface; local-directory and S3-compatible backends
- Client-side encryption, user holds the key
- Restore onto a clean machine as a **tested** path, not an assumed one
- `tawn backup create/restore/verify`

It is also the first thing that could be charged for, per the commercial line in
`OSS-ROADMAP.md` — the revenue path and the data-loss fix are the same work.

## Then — the authority layer (stages 16–21)

In order, because each depends on the last:

| Stage | Work |
|---|---|
| 16 | Extract `PolicyEngine` from filesystem mediation. Closes the coupling behind the REVIEW-2026-07-27 `135:6` gap; worth doing on its own merits |
| 17 | Registrable action types, so plugins contribute action classes and grant schema |
| 18 | Domain principals — per-domain grants, model allowlist, spend ceiling, sensitivity policy |
| 19 | Signed evidence bundles |
| 20 | `may_i(action)` / `evidence(id)` over MCP — the largest strategic surface here |
| 21 | `AnchorTarget` port + OpenTimestamps |

## Known gaps worth fixing when convenient

Small, independent, none blocking.

- **Attribution misses relative paths in shell commands.** When an agent edits via
  a script using a relative path, no absolute path reaches the transcript. Options:
  resolve relative candidates against the project root and require the file to
  exist, or accept the gap and document it.
- **`_MAX_DEPTH = 6`** in `transcripts.py` is a guess. Nothing has been measured
  about how deep tool payloads actually nest.
- **Audit log rotation is unbounded.** Files are currently 0.0 MB, so this is a
  future problem, not a present one.
- **Windows and macOS are CI-verified only** — never confirmed by a real user.
- **First-run still requires PostgreSQL** with no zero-setup fallback.
- **`tsc --noEmit` does not catch what `tsc -b` catches.** A syntax error inside a
  multi-line import passed `--noEmit` and failed the build. Verify frontend changes
  with the command the build actually runs.

## Deliberately not next

- **Web3 layer** (`tawn-hq/docs/WEB3_ROADMAP.md`). Self-contained, specced, and
  explicitly not on the path to 1.0. Do not start it before durability and the
  authority layer land — this repo already has one maintainer.
- **Sharing / Stage 11.** Moved from first to ninth on purpose: its spend caps,
  guest attribution and audit-trust story each get built once on top of the
  authority layer instead of twice.
