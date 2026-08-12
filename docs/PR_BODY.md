## What this changes

The Observer stops overstating what it knows. It previously recorded only what
inotify told it while running, and a note listing four files read as "these four
changed" when the truth was "these four were observed". This adds git and
filesystem reconciliation to close that gap, replaces an attribution heuristic
that could only ever work in real time, moves review notes somewhere they can
actually be read, and fixes three defects found while testing it — a 500 on
`/api/history`, floats on the money path, and a watcher that reported readiness
before it was ready.

## Why

Four separate problems, all found by running the thing rather than reading it:

- **The record was incomplete and did not say so.** Measured: the recursive watch
  takes ~15s to arm (15.8s across ~14,000 directories), during which edits vanish
  with no error. Anything done while the daemon was stopped — which is most work,
  most of the time — left no trace at all.
- **Attribution was structurally broken for anything not happening right now.**
  `agent_sessions_touched` compares a file's mtime against a session log's
  *current* mtime, and an active log's mtime is always ~now. A file edited 774
  minutes earlier returned no hits; the same call against `now` returned
  `claude_code`. 77% of swept events landed as `unknown`.
- **Notes were unreadable and in the wrong place.** Written to `grants.write[0]`,
  so every project's notes went to whichever directory was granted first — notes
  about `engine` were being written into the `tawn` repository. Nothing in the CLI
  or the web UI rendered them.
- **One corrupt file took down an endpoint.** A session log containing ~760 KB of
  binary (from the since-fixed attachment defect) made every `/api/history`
  request fail with `JSONDecodeError`.

## How it was verified

```
$ .venv/bin/python -m pytest tests/ -q
1228 passed, 697 warnings in 317.48s

$ npx tsc -b && npm run build
✓ built in 2m 16s

$ pipx install . --force && tawn observe note tawn
## 22:12 – 22:35 · tawn
**1 files · +17 −0 · closed by idle**
Attribution: 1 likely unknown
Coverage: observed live, reconciled against git at 23:44
```

1228 passing, up from 1171 — 57 new tests. Zero regressions.

Verified against real data, not only fixtures:

- **Sweep on real projects.** A first run would have filed **2,415 historical
  events** under today's session (198 commits of one repo expanding to 1,613 file
  events). Now baselines instead: 42 events, all genuinely uncommitted work.
  Second run: `nothing to reconcile` across all four projects.
- **Arming gap closed.** Created a file *during* the arming window, then ran
  `tawn observe start`: armed at 19.3s, sweep fired, and the file the watcher
  could not have seen was recorded as
  `added _sigint-check.tmp.md basis=sweep-scan actor=agent:claude_code`.
- **Non-git detection.** `certin/docs` has no repository; the snapshot scan
  detected a new file there and correctly ignored a `touch` that changed no
  content.
- **History.** 15 sessions load in 0.67s with the corrupt file flagged rather than
  fatal, and one real entry recovered from it.
- **Ctrl-C shutdown** on `observe start`: exit 0, no core dump.

## What a tool cannot check

**Scope.** Wider than one concern, and I would understand a request to split it.
The through-line is "the observer's record should be trustworthy", but three of the
fixes (history 500, money floats, `Checkbox` gaining a `disabled` prop) were found
*while* doing that rather than being part of it. The history fix in particular is
independent and could be pulled out.

**`sensitive` content.** Unchanged. Review notes route through
`default_router(..., sensitive=not use_cloud)`, so local-only remains the default
and filtering still happens before provider selection. `--cloud` and cloud model
selection are opt-in, and both the CLI help and the UI say they send **file paths
and line counts** — never file contents — off the machine.

**Trust boundaries.** One new place untrusted content meets a privileged surface:
agent transcripts are now parsed. They are read as data only — JSON parsed, paths
extracted by regex, never executed or interpolated. A malformed transcript is
caught and logged rather than propagating. The paths are stored in
`ObservedEvent.path` and rendered as text.

**Destructive operations.** `tawn key delete` is new and confirms first, and
reports honestly when a key survives in the environment (a process cannot unset a
parent shell's variable, so claiming "removed" would be a lie the user discovers
later). `--dry-run` on the sweep writes nothing, verified by test. Nothing else
deletes.

**Docs.** `PRD.md` substantially rewritten (its stated premise was obsolete —
per-vendor memory shipped, so "assistants don't remember you" is no longer the
opportunity), `ROADMAP.md` gained stages 16–23 and four decision-log entries,
`docs/NEXT.md` added.

## Anything reviewers should look at closely

**`observer/sweep.py` dedup, two different scopes.** Path-level *within* a run
(commit and scan seeing one change under different labels), `(path, kind)` against
history (an add and a later delete are two real events). I had this wrong twice: a
flat 30-day window swallowed genuine changes, then path-only matching against
history silently dropped a deletion. Both found by running it, not by a test — the
unit tests passed while the second bug was live.

**`transcripts.py` — deliberately format-agnostic.** Each record is walked for a
timestamp and for absolute paths, rather than three bespoke parsers for Claude
Code, Codex and Gemini CLI. Judgement call: fewer things to break when a vendor
changes schema, at the cost of being less precise than a real parser.

**A known limitation, not a bug.** When an agent edits through a shell script using
a *relative* path, no absolute path reaches the transcript, so the change is
unattributable. This is why the unknown rate on my own data is still high — I work
that way. For agents using ordinary file tools, attribution works.

**`MAX_COMMIT_AGE_DAYS = 14` and `MAX_COMMITS = 200`** are judgement, not
measurement. Both bounds exist because they fail differently: a busy day exceeds
the count, a dormant month exceeds the age.

**Frontend verification.** `tsc --noEmit` passed a file that `tsc -b` rejected — a
helper inserted inside a multi-line `import {`. Frontend changes here are verified
with `tsc -b`, the command the build actually runs.

## Follow-ups deliberately left out

Listed in `docs/NEXT.md`. The two that matter: **encrypted backup** (stage 22 — the
only outstanding item where delay risks unrecreatable loss), and **`ollama pull
qwen2.5:7b`**, because qwen3:0.6b writes analysis that invents filenames. The facts
in a note are safe — they are rendered from the database and a model answer that
fails validation is discarded — but the prose is not yet usable.

Also unrelated to this diff but worth knowing: a GitHub token was sitting in
`.git/config` in plaintext. It has been stripped from the remote and **needs
revoking**.
