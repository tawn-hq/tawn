# Observer git reconciliation sweep — design

Date: 2026-07-30 · Status: proposed, not implemented
Relates to: Stage 9 (Ambient Observer), `docs/ROADMAP.md` stages 16–23

## The problem

The Observer only knows what inotify told it while it was running. Three windows
where that is false, all measured or observed on this machine:

1. **Arming.** `watchfiles` walks the granted trees before the recursive watch
   exists — **15.8s** across ~14,000 directories (14.9s with the event pre-filter;
   the Rust layer walks regardless, so filtering does not fix this). Anything
   edited in that window is never seen. This was reproduced twice while verifying
   the observer, and both times looked like "the observer is broken".
2. **Downtime.** The watcher runs inside `tawn web` or `tawn observe start`. Work
   done with it stopped — which is most work, for most users, most of the time —
   leaves no trace at all.
3. **Missed events.** inotify drops events under queue overflow, and it does not
   see changes made by another machine to a synced directory, or by a
   `git checkout` that rewrites hundreds of files at once.

The consequence is worse than incompleteness. A review note that lists four files
reads as *"these four files changed"*, when the truth is *"these four were
observed"*. That is the same class of defect as the model echoing a corrupted path
into a note: a record that overstates its own completeness.

## What this adds

A **sweep**: reconcile the observer's record against git, which already knows what
changed whether Tawn was watching or not. inotify supplies liveness and precise
timing; git supplies completeness.

Not a replacement. inotify sees edits to untracked and ignored files, and it sees
*when* something happened. Git sees everything that persisted, and nothing that
was reverted before it looked.

## Scope

**In:** git-tracked working-tree changes and new commits for projects where
`Project.is_git` is true.

**Out:**
- Non-git projects. `certin/docs` is already watched and has no repository; the
  sweep simply skips it, and the note says so rather than implying coverage.
- File contents and diffs. `ObservedEvent` deliberately holds no content, and
  that does not change.
- Untracked files that git ignores. If the user's `.gitignore` excludes it, the
  sweep treats it as out of scope; inotify plus Tawn's own ignore rules remain
  the only path for those.

## Data model

**No schema change to `ObservedEvent`.** The sweep writes the same rows through the
same `record_event()` path, so everything downstream — notes, attribution
summaries, the web page — works with no modification.

One new table, following the `LedgerWatermark` precedent already in
`memory/schema.py`:

```python
class ObserverWatermark(Base):
    """How far the sweep has reconciled one project."""
    __tablename__ = "observer_watermark"

    project      = Column(String(128), primary_key=True)
    last_commit  = Column(String(64), nullable=True)   # HEAD at last sweep
    tree_digest  = Column(String(64), nullable=True)   # digest of dirty-set state
    swept_at     = Column(DateTime(timezone=True), nullable=False)
```

`last_commit` makes commit reconciliation cheap: `git log <last_commit>..HEAD`.
`tree_digest` is a hash over the sorted `(path, size, mtime_ns)` of the dirty set,
so an unchanged working tree costs one comparison instead of one row per file.

Two new `ObservedEvent.basis` values — the column is `String(16)`, so both fit:

- `sweep-commit` — reconstructed from commit history
- `sweep-tree` — reconstructed from working-tree state

`basis` is already surfaced per line in the web UI (`via session`, `via git`), so
these appear automatically and a reader can tell a reconstructed row from an
observed one. That distinction is the point.

## Mechanism

### 1. Commits since the watermark

```
git log --numstat --format=%H%x00%an%x00%ae%x00%cI <last_commit>..HEAD
```

Gives, per commit: hash, author name, author email, ISO timestamp, and per-file
added/removed counts. Everything `ObservedEvent` needs, with real line deltas —
**better** than the live watcher, whose `_deltas()` reports current file length as
`lines_added` because it has no previous version to compare against.

Attribution reuses `_match_agent_identity()` against `cfg.agent_identities`
unchanged, so a commit authored by `noreply@anthropic.com` attributes to the agent
exactly as the live tier-1 path does. Confidence `high`, basis `sweep-commit`.

### 2. Working-tree changes

```
git status --porcelain=v1 -z --untracked-files=normal
git diff --numstat            # unstaged
git diff --numstat --cached   # staged
```

Line deltas come from `--numstat`; untracked files report their line count as
added, matching current live behaviour.

**Attribution here is genuinely weaker, and must say so.** There is no commit, so
tier 1 is unavailable. The sweep runs the existing session-log correlation
(`agent_sessions_touched`) against each file's mtime — the same tier 2 the live
watcher uses. Where that hits, `high` / `sweep-tree`. Where it does not, the actor
is `unknown` with `low` confidence, **never** a timing guess: the timing heuristic
depends on burst structure the sweep did not witness, and inventing one would be
the exact "guess rendered as fact" failure the tiering exists to prevent.

### 3. Deduplication

The sweep must not double-count what inotify already recorded. Rule:

> A `(project, path, kind)` already present in the currently open session, or in
> any session whose window contains the change's timestamp, is skipped.

Implemented as one indexed query per project over
`ObservedEvent.project == p AND ts >= window_start`, loaded into a set. The
existing `session_id`/`project` indexes cover it.

Where the sweep has *better* data for a row inotify already recorded — real
`lines_added`/`lines_removed` from `--numstat` versus the live watcher's
file-length approximation — it **updates the existing row** rather than inserting
a second one, and leaves `basis` as the original observation. The record should say
who saw it first and carry the best numbers available; two rows for one change
would inflate every count in every note.

### 4. Session placement

- A commit reconciles into a session opened at the commit's authored time and
  closed immediately with `closed_by="commit"`, matching what the live watcher
  does on a commit event.
- Working-tree changes join the project's currently open session if one exists,
  otherwise open one and leave it open — the work is, by definition, still
  uncommitted.

`record_event()` already implements both behaviours. No new session logic.

## Surfaces

```
tawn observe sweep [project] [--dry-run]
```

`--dry-run` prints what would be recorded and writes nothing. Given this touches
the audit trail, being able to look before committing to it matters.

The sweep also runs automatically at two points:

- **On watcher arm.** Immediately after `on_armed` fires, closing the ~15s window
  structurally rather than trying to shrink it.
- **Before a review.** `write_note()` composes from whatever is in the database, so
  reconciling first is what makes the note's file list actually complete.

HTTP: `POST /api/observer/sweep?project=&dry_run=`, and a button on the Observer
page beside *write notes*. The existing sessions list needs no change — swept rows
appear as ordinary events with a distinguishing `basis`.

## Honest limits — to be stated in the note, not just here

The note header should carry the coverage claim so a reader is not misled:

```
6 files · +55 −4 · closed by manual
Attribution: 4 agent:claude_code, 2 unknown
Coverage: observed live, reconciled against git at 14:06
```

And for a project the sweep cannot help:

```
Coverage: observed live only — not a git repository
```

Remaining gaps after this lands, which the sweep does **not** close:

- Changes to git-ignored files while the watcher was down. Unknowable from either
  source.
- Work reverted before the sweep ran. Git has no record; that is arguably correct.
- **Who** made an uncommitted change when no agent session log corroborates it.
  Reported as `unknown`, not guessed.

## Testing

Fixture: a real temporary git repository (`git init`, commits with controlled
author identity via `-c user.name`/`-c user.email`). Subprocess `git`, not a
library — the parsing is the thing under test, and mocking `git log` output would
test the mock.

Cases that must hold:

1. Commit by an agent identity → `agent:*`, `high`, `sweep-commit`.
2. Commit by the user → `human`, `high`, `sweep-commit`.
3. Uncommitted change with a correlating session log → `high`, `sweep-tree`.
4. Uncommitted change with no correlation → `unknown`, `low` — **never** a timing
   guess.
5. A path inotify already recorded is not duplicated.
6. Same path with better `--numstat` deltas updates the row and preserves the
   original `basis`.
7. Second sweep with no intervening change writes nothing (watermark works).
8. Non-git project is skipped without raising.
9. `--dry-run` writes zero rows.
10. A rewritten history (`last_commit` no longer reachable) falls back to a
    tree-only sweep instead of failing — `git log A..B` errors on an unknown `A`.

## Sequencing

Depends on nothing in stages 16–23; it is self-contained and could land next.
It does, however, get materially better after **stage 19 (signed evidence
bundles)**, where a reconstructed row's weaker provenance becomes part of the
signed record rather than only a column value.

Rough shape: watermark table and migration, commit reconciliation, tree
reconciliation, dedup, CLI, then auto-trigger on arm and before review. Each is
independently testable, and the first two already deliver most of the value.

## Rejected alternatives

**Polling the filesystem instead.** Walking ~14,000 directories on a timer costs
more than the arming walk it replaces and still misses everything that happened
while Tawn was off.

**Storing diffs so changes can be reconstructed exactly.** Makes Tawn an
unversioned second copy of the user's source that outlives deletion — the reason
`ObservedEvent` holds no content today. Git already is that copy, and it is the
user's.

**A git hook instead of a sweep.** A `post-commit` hook covers commits and nothing
else, has to be installed per repository, and silently stops working when a repo
is re-cloned. The sweep needs no cooperation from the repository.

**Trusting mtime alone for attribution.** mtime says when, never who. Coarse and
easily wrong — the very reason the confidence tiers exist.
