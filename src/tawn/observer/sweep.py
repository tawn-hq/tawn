"""Reconcile the observer's record against git.

The watcher only knows what inotify told it while it was running. Three windows
where that is false, all measured on a real machine: the ~15s the recursive watch
takes to arm, any period the daemon was stopped, and events dropped under queue
overflow or written by a `git checkout` touching hundreds of files at once.

The consequence is worse than incompleteness. A note listing four files reads as
"these four changed" when the truth is "these four were observed" — a record
overstating its own completeness, which is the failure the confidence tiers exist
to prevent.

So: inotify supplies liveness and precise timing, git supplies completeness.
Neither replaces the other. inotify sees edits to untracked and ignored files and
knows *when*; git sees everything that persisted and nothing reverted before it
looked.

Rows written here go through the same `record_event()` as live events, so notes,
attribution summaries and the web page need no changes. They are distinguishable
only by `basis`, which is deliberate — a reader must be able to tell a
reconstructed row from an observed one.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from tawn.capability.grants import Grants
from tawn.ignore import load_ignore_patterns, should_ignore
from tawn.memory.schema import ObservedEvent, ObserverWatermark
from tawn.observer.attribution import Attribution, _match_agent_identity
from tawn.observer.config import ObserverConfig, load_observer_config
from tawn.observer.projects import Project, discover_projects, tier_enabled
from tawn.observer.sessions import close_session, current_session, record_event

#: Basis values for reconstructed rows. `ObservedEvent.basis` is String(16).
_log = logging.getLogger(__name__)

SWEEP_COMMIT = "sweep-commit"
SWEEP_TREE = "sweep-tree"

#: Caps how much history one sweep will read. Both bounds exist because they fail
#: differently: a busy day can exceed the count, and a dormant month can exceed
#: the age. Measured on real repositories, 198 commits of history expanded to
#: 1,613 file events — reconciling that into *today's* session would bury the
#: actual work under years of unrelated history.
MAX_COMMITS = 200
MAX_COMMIT_AGE_DAYS = 14

#: NUL separates the header fields, so paths containing newlines, tabs or quotes
#: survive intact. Two spellings on purpose: argv cannot carry a literal NUL, so
#: the format string sends git the four characters `%x00` and git emits the real
#: byte, which is what the output is then split on.
_SEP_FMT = "%x00"
_SEP = "\x00"


@dataclass
class SweepResult:
    """What one sweep did. Every field is reported rather than summed into a
    single number, because "wrote 4" and "updated 4 and skipped 30" are very
    different outcomes for a record."""

    project: str
    commits_read: int = 0
    events_added: int = 0
    events_updated: int = 0
    skipped_existing: int = 0
    tree_files: int = 0
    reason: str = ""
    dry_run: bool = False
    paths: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.events_added or self.events_updated)


def _git(root: Path, *args: str, timeout: int = 30) -> str | None:
    """Run git, returning stdout or None. Never raises.

    A repository that is mid-rebase, corrupt, or simply not there must degrade the
    sweep to "nothing to reconcile" rather than take down a review.
    """
    try:
        p = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def head_commit(root: Path) -> str | None:
    out = _git(root, "rev-parse", "HEAD")
    return out.strip() if out else None


def _commit_reachable(root: Path, sha: str) -> bool:
    """Whether `sha` is still in this history.

    A rebase or a force-push makes the stored watermark unreachable, and
    `git log <gone>..HEAD` then fails. Checking first turns that into a tree-only
    sweep instead of an error.
    """
    return _git(root, "cat-file", "-e", f"{sha}^{{commit}}") is not None


# ── commit reconciliation ─────────────────────────────────────────────────────


@dataclass
class CommitChange:
    sha: str
    author: str
    email: str
    when: datetime.datetime
    path: str
    added: int
    removed: int


def _parse_iso(raw: str) -> datetime.datetime:
    try:
        dt = datetime.datetime.fromisoformat(raw.strip())
    except ValueError:
        return datetime.datetime.now(datetime.timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def commit_changes(
    root: Path, since: str, limit: int = MAX_COMMITS, max_age_days: int = MAX_COMMIT_AGE_DAYS
) -> list[CommitChange]:
    """Per-file changes for commits after `since`.

    `--numstat` gives real added/removed counts — better than the live watcher,
    whose `_deltas()` reports current file length as `lines_added` because it has
    no previous version to compare against.

    Age-bounded as well as count-bounded. If Tawn has not run for months the
    watermark is ancient, and reconciling every commit since would file a quarter
    of history under one afternoon's session.
    """
    fmt = f"%H{_SEP_FMT}%an{_SEP_FMT}%ae{_SEP_FMT}%cI"
    out = _git(
        root, "log", "--numstat", "--no-merges", f"--format={fmt}",
        f"--max-count={limit}", f"--since={max_age_days}.days.ago", f"{since}..HEAD",
    )
    if not out:
        return []

    changes: list[CommitChange] = []
    sha = author = email = ""
    when = datetime.datetime.now(datetime.timezone.utc)
    for line in out.splitlines():
        if not line.strip():
            continue
        if _SEP in line:
            parts = line.split(_SEP)
            if len(parts) == 4:
                sha, author, email, when_raw = parts
                when = _parse_iso(when_raw)
            continue
        cols = line.split("\t")
        if len(cols) != 3 or not sha:
            continue
        added_s, removed_s, path = cols
        # "-" marks a binary file: git cannot count lines, so neither do we.
        added = int(added_s) if added_s.isdigit() else 0
        removed = int(removed_s) if removed_s.isdigit() else 0
        changes.append(CommitChange(sha, author, email, when, path.strip(), added, removed))
    return changes


def _commit_attribution(c: CommitChange, cfg: ObserverConfig) -> Attribution:
    """Tier 1, unchanged: a commit carries its author, so this is evidence."""
    matched = (
        _match_agent_identity(c.author, cfg.agent_identities)
        or _match_agent_identity(c.email, cfg.agent_identities)
    )
    actor = f"agent:{matched}" if matched else "human"
    return Attribution(actor, "high", SWEEP_COMMIT)


# ── working-tree reconciliation ───────────────────────────────────────────────


@dataclass
class TreeChange:
    path: str
    kind: str
    added: int
    removed: int


def _numstat(root: Path, *args: str) -> dict[str, tuple[int, int]]:
    out = _git(root, "diff", "--numstat", *args)
    stats: dict[str, tuple[int, int]] = {}
    for line in (out or "").splitlines():
        cols = line.split("\t")
        if len(cols) != 3:
            continue
        a, r, path = cols
        stats[path.strip()] = (
            int(a) if a.isdigit() else 0,
            int(r) if r.isdigit() else 0,
        )
    return stats


def tree_changes(root: Path) -> list[TreeChange]:
    """Uncommitted work: staged, unstaged and untracked.

    Git-ignored files are out of scope by design — if the user's `.gitignore`
    excludes it, inotify plus Tawn's own ignore rules remain the only path.
    """
    out = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
    if out is None:
        return []
    stats = {**_numstat(root, "--cached"), **_numstat(root)}

    changes: list[TreeChange] = []
    fields = [f for f in out.split("\0") if f]
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] == "R":
            # Rename: the following NUL field is the source path. Consume it, and
            # record the destination — that is where the content now lives.
            i += 1
        kind = "deleted" if "D" in code else ("added" if code in ("??", "A ", "AM") else "modified")
        added, removed = stats.get(path, (0, 0))
        if not added and not removed and kind != "deleted":
            added = _count_lines(root / path)
        changes.append(TreeChange(path, kind, added, removed))
    return changes


def _count_lines(path: Path) -> int:
    try:
        with path.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def tree_digest(root: Path, changes: list[TreeChange]) -> str:
    """Digest of the dirty set, so an unchanged tree short-circuits the sweep."""
    h = hashlib.sha256()
    for c in sorted(changes, key=lambda x: x.path):
        try:
            st = (root / c.path).stat()
            h.update(f"{c.path}:{st.st_size}:{st.st_mtime_ns}:{c.kind}".encode())
        except OSError:
            h.update(f"{c.path}:missing:{c.kind}".encode())
    return h.hexdigest()


def _tree_attribution(
    home: Path,
    project: Project,
    path: Path,
    cfg: ObserverConfig,
    grants: Grants,
    index: dict | None = None,
) -> Attribution:
    """Who changed an uncommitted file. Evidence first, then nothing.

    Order matters. The transcript index is checked first because it is *evidence*
    — this agent named this exact file at this time. The mtime heuristic is only
    consulted as a fallback, and it can only ever fire for a change made moments
    ago, since it compares against a session log's current mtime.

    No timing heuristic and no guess: without a commit or a transcript match the
    answer is `unknown`, which is the honest one.
    """
    if not tier_enabled(grants, "agents"):
        return Attribution("unknown", "low", SWEEP_TREE)
    try:
        ts = path.stat().st_mtime
    except OSError:
        return Attribution("unknown", "low", SWEEP_TREE)

    if index:
        from tawn.observer.transcripts import attribute_from_index

        got = attribute_from_index(index, str(path), ts)
        if got:
            actor, confidence = got
            return Attribution(actor, confidence, SWEEP_TREE)

    from tawn.observer.attribution import agent_sessions_touched

    hits = agent_sessions_touched(home, project, ts, cfg)
    if hits:
        return Attribution(f"agent:{hits[0]}", "high", SWEEP_TREE)
    return Attribution("unknown", "low", SWEEP_TREE)


# ── snapshot scan (git-independent) ───────────────────────────────────────────
#
# What an editor or a backup tool does, and the only source that works for a
# project with no repository — `certin/docs` among the currently watched ones.
#
# Two-stage on purpose. `(size, mtime_ns)` is the cheap gate; content is hashed
# only when that differs. The second stage is what stops a `touch`, a checkout of
# identical bytes, or a formatter that rewrites a file unchanged from being
# recorded as an edit. Reporting those would fill the log with changes that never
# happened, which is the same overstatement the sweep exists to correct.

#: Files larger than this are tracked by stat alone. Hashing a 200 MB asset on
#: every sweep costs more than the change detection is worth, and a file that big
#: is not source someone is editing.
MAX_HASH_BYTES = 8_000_000

#: Ceiling on tracked files per project, so a mistakenly granted home directory
#: degrades to a truncated scan rather than an unbounded one. Reported when hit.
MAX_SCAN_FILES = 20_000


def _digest_and_lines(path: Path) -> tuple[str | None, int]:
    """`(sha256, line count)`, or `(None, 0)` when the file is too big or unreadable."""
    try:
        if path.stat().st_size > MAX_HASH_BYTES:
            return None, 0
        h = hashlib.sha256()
        lines = 0
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                h.update(block)
                lines += block.count(b"\n")
        return h.hexdigest(), lines
    except OSError:
        return None, 0


def _walk(root: Path, ignore) -> tuple[list[Path], bool]:
    """Files under `root` worth tracking, and whether the scan was truncated."""
    from tawn.observer.watch import WATCH_EXCLUDE_DIRS

    found: list[Path] = []
    stack = [root]
    truncated = False
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_symlink():
                # Following symlinks risks leaving the granted root entirely and
                # can loop. The target is scanned anyway if it is itself granted.
                continue
            if e.is_dir():
                if e.name not in WATCH_EXCLUDE_DIRS:
                    stack.append(e)
            elif e.is_file():
                if len(found) >= MAX_SCAN_FILES:
                    truncated = True
                    return found, truncated
                if not should_ignore(e, *ignore):
                    found.append(e)
    return found, truncated


@dataclass
class ScanChange:
    path: Path
    kind: str
    added: int
    removed: int


def scan_changes(
    session: Session, project: Project, ignore, now: datetime.datetime
) -> tuple[list[ScanChange], bool]:
    """Diff the tree against the stored snapshot, and update the snapshot.

    Returns `(changes, truncated)`. Line deltas are **net**: content is not kept,
    so a file that grew by five lines reports `+5`, and one that shrank by three
    reports `−3`. A true added/removed split needs the previous content, which
    `ObservedEvent` deliberately does not store — for git-tracked files the commit
    path above supplies the real numbers instead.
    """
    from tawn.memory.schema import FileSnapshot

    rows = {
        r.path: r
        for r in session.query(FileSnapshot)
        .filter(FileSnapshot.project == project.name)
        .all()
    }
    files, truncated = _walk(project.root, ignore)
    changes: list[ScanChange] = []
    seen: set[str] = set()

    for f in files:
        key = str(f)
        seen.add(key)
        try:
            st = f.stat()
        except OSError:
            continue
        row = rows.get(key)

        if row is not None and row.size == st.st_size and row.mtime_ns == st.st_mtime_ns:
            continue  # cheap gate: nothing moved

        digest, lines = _digest_and_lines(f)
        if row is None:
            changes.append(ScanChange(f, "added", lines, 0))
            session.add(
                FileSnapshot(
                    project=project.name, path=key, size=st.st_size,
                    mtime_ns=st.st_mtime_ns, digest=digest, lines=lines, seen_at=now,
                )
            )
            continue

        if digest is not None and digest == row.digest:
            # Touched, not changed. Refresh stat so the cheap gate works next
            # time, and record nothing — this is the false positive the second
            # stage exists to suppress.
            row.size, row.mtime_ns, row.seen_at = st.st_size, st.st_mtime_ns, now
            continue

        delta = lines - (row.lines or 0)
        changes.append(
            ScanChange(f, "modified", max(delta, 0), max(-delta, 0))
        )
        row.size, row.mtime_ns, row.digest, row.lines, row.seen_at = (
            st.st_size, st.st_mtime_ns, digest, lines, now,
        )

    for key, row in rows.items():
        if key in seen:
            continue
        if truncated:
            # A truncated scan did not look everywhere, so absence is not
            # evidence of deletion. Leave the row alone.
            continue
        changes.append(ScanChange(Path(key), "deleted", 0, row.lines or 0))
        session.delete(row)

    return changes, truncated


# ── dedup ─────────────────────────────────────────────────────────────────────


def _existing_index(
    session: Session, project: str
) -> dict[tuple[str, str], ObservedEvent]:
    """`(path, kind)` → row, for events in the project's currently open session.

    Scoped to the open session rather than a time window. Dedup exists to avoid
    re-recording what the live watcher just saw; it must not suppress a genuinely
    new change. A flat 30-day window did exactly that — an uncommitted edit was
    swallowed because the same file had been committed a week earlier, which are
    two different changes.

    Idempotence across repeated sweeps comes from the watermarks instead:
    `last_commit` for commits, `tree_digest` for the working tree, and the file
    snapshot for the scan.
    """
    sess = current_session(session, project)
    if sess is None:
        return {}
    rows = (
        session.query(ObservedEvent)
        .filter(ObservedEvent.session_id == sess.id)
        .all()
    )
    return {(r.path, r.kind): r for r in rows}


def _better_deltas(row: ObservedEvent, added: int, removed: int) -> bool:
    """Whether the sweep's numbers improve on what is stored.

    The live watcher records current file length as `lines_added` and zero
    removed, because it never sees the previous version. `--numstat` knows both.
    Updating in place rather than inserting keeps one change as one row — a second
    row would inflate every count in every note.
    """
    return (added, removed) != (row.lines_added, row.lines_removed) and (
        removed > 0 or added != row.lines_added
    )


# ── the sweep ─────────────────────────────────────────────────────────────────


SWEEP_SCAN = "sweep-scan"


def _sweep_scan(
    session: Session,
    home: Path,
    project: Project,
    cfg: ObserverConfig,
    grants: Grants,
    ignore,
    res: SweepResult,
    now: datetime.datetime,
    dry_run: bool,
    seeding: bool,
    index: dict | None = None,
) -> None:
    """Record what the snapshot scan found, deduped against existing rows."""
    # `seeding` comes from the watermark, not from the snapshot being empty: a
    # project that happened to be empty at baseline would otherwise never leave
    # seeding mode and would never report a change.
    changes, truncated = scan_changes(session, project, ignore, now)
    if dry_run:
        # The scan mutates the snapshot as it walks, which a dry run must not do.
        session.rollback()

    if truncated:
        res.reason = (
            f"{res.reason + '; ' if res.reason else ''}"
            f"scan truncated at {MAX_SCAN_FILES} files — deletions not detected"
        )
    if seeding:
        res.reason = (
            f"{res.reason + '; ' if res.reason else ''}"
            f"baseline taken for {len(changes)} file(s) — changes reported from the next sweep"
        )
        return
    if not changes:
        return

    existing = _existing_index(session, project.name)
    # Two different dedup scopes, because they answer different questions.
    #
    # Within this run, dedup on path alone: if the commit step already recorded a
    # file, the scan seeing it as "added" is the same change wearing a different
    # label, and two rows would inflate every count in the note.
    #
    # Against earlier events, dedup on (path, kind): a file added in one sweep and
    # deleted before the next is two real events. Matching on path alone there
    # silently swallowed the deletion — found by running it, not by a test.
    this_run = set(res.paths)
    for c in changes:
        if str(c.path) in this_run or (str(c.path), c.kind) in existing:
            res.skipped_existing += 1
            continue
        res.events_added += 1
        res.paths.append(str(c.path))
        if dry_run:
            continue
        attr = _tree_attribution(Path(home), project, c.path, cfg, grants, index)
        record_event(
            session, project.name, str(c.path), c.kind,
            Attribution(attr.actor, attr.confidence, SWEEP_SCAN), now,
            lines_added=c.added, lines_removed=c.removed,
        )


def _mark_swept(
    session: Session,
    mark: ObserverWatermark | None,
    project: str,
    head: str | None,
    digest: str | None,
    now: datetime.datetime,
) -> None:
    """Record that this project has been swept.

    Written for non-git projects too: the row is what distinguishes a first sweep
    (take a baseline) from a later one (report changes), and that question has
    nothing to do with whether a repository exists.
    """
    if mark is None:
        session.add(
            ObserverWatermark(
                project=project, last_commit=head, tree_digest=digest, swept_at=now,
            )
        )
    else:
        mark.last_commit, mark.tree_digest, mark.swept_at = head, digest, now
    session.commit()


def sweep_project(
    session: Session,
    home: Path,
    project: Project,
    *,
    dry_run: bool = False,
    now: datetime.datetime | None = None,
    index: dict | None = None,
) -> SweepResult:
    res = SweepResult(project=project.name, dry_run=dry_run)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    grants = Grants.load(Path(home) / "grants.yaml")
    cfg = load_observer_config(Path(home))
    ignore = load_ignore_patterns(Path(home))

    mark = session.get(ObserverWatermark, project.name)
    first_sweep = mark is None

    if not project.is_git:
        # No repository, so the snapshot scan is the only source — and the reason
        # it exists. `certin/docs` is a real example among the watched projects.
        res.reason = "not a git repository — snapshot scan only"
        _sweep_scan(
            session, home, project, cfg, grants, ignore, res, now, dry_run,
            seeding=first_sweep, index=index,
        )
        if not dry_run:
            _mark_swept(session, mark, project.name, None, None, now)
        return res
    since = mark.last_commit if mark and mark.last_commit else None
    if since and not _commit_reachable(project.root, since):
        # Rewritten history. Fall back to a tree-only sweep rather than failing.
        since = None
        res.reason = "history rewritten — commit range reset"

    existing = _existing_index(session, project.name)

    def _skip(rel: str) -> bool:
        return should_ignore(project.root / rel, *ignore)

    # 1. commits — skipped on a first sweep for the same reason the scan takes a
    # baseline: there is no gap to fill, because nothing was ever watched. A real
    # dry run showed the alternative filing 2,415 historical events under today.
    commits = [] if since is None else commit_changes(project.root, since)
    res.commits_read = len({c.sha for c in commits})
    for c in commits:
        if _skip(c.path):
            continue
        key = (str(project.root / c.path), "modified")
        if key in existing:
            res.skipped_existing += 1
            continue
        res.events_added += 1
        res.paths.append(str(project.root / c.path))
        if dry_run:
            continue
        record_event(
            session, project.name, str(project.root / c.path), "modified",
            _commit_attribution(c, cfg), c.when,
            lines_added=c.added, lines_removed=c.removed,
        )
        sess = current_session(session, project.name)
        if sess is not None:
            close_session(session, sess, c.when, "commit")

    # 2. working tree
    tchanges = [t for t in tree_changes(project.root) if not _skip(t.path)]
    res.tree_files = len(tchanges)
    digest = tree_digest(project.root, tchanges)
    unchanged_tree = bool(mark and mark.tree_digest == digest)

    if not unchanged_tree:
        for t in tchanges:
            abs_path = project.root / t.path
            row = existing.get((str(abs_path), t.kind))
            if row is not None:
                if _better_deltas(row, t.added, t.removed):
                    res.events_updated += 1
                    if not dry_run:
                        # Keep the original `basis`: the record should say who saw
                        # it first, while carrying the best numbers available.
                        row.lines_added, row.lines_removed = t.added, t.removed
                        session.commit()
                else:
                    res.skipped_existing += 1
                continue
            res.events_added += 1
            res.paths.append(t.path)
            if dry_run:
                continue
            record_event(
                session, project.name, str(abs_path), t.kind,
                _tree_attribution(Path(home), project, abs_path, cfg, grants, index), now,
                lines_added=t.added, lines_removed=t.removed,
            )

    # 3. snapshot scan — catches what git cannot see: ignored files, and any file
    # in a project where the working tree is clean but the snapshot disagrees
    # (a change made and reverted while the watcher was down leaves git silent).
    _sweep_scan(
        session, home, project, cfg, grants, ignore, res, now, dry_run,
        seeding=first_sweep, index=index,
    )

    if not dry_run:
        _mark_swept(session, mark, project.name, head_commit(project.root), digest, now)
    return res


def sweep(
    session: Session,
    home: Path,
    project: str | None = None,
    *,
    dry_run: bool = False,
    now: datetime.datetime | None = None,
) -> list[SweepResult]:
    """Reconcile one project, or every watched project."""
    grants = Grants.load(Path(home) / "grants.yaml")
    projects = [p for p in discover_projects(grants) if project in (None, p.name)]
    # Built once for the whole run: parsing megabytes of agent transcripts per
    # project would cost more than the reconciliation itself.
    index: dict = {}
    if projects:
        try:
            from tawn.observer.transcripts import build_index

            index = build_index(Path(home), tuple(str(p.root) for p in projects))
        except Exception:
            _log.warning("transcript index unavailable", exc_info=True)
    return [
        sweep_project(session, Path(home), p, dry_run=dry_run, now=now, index=index)
        for p in projects
    ]


def coverage_line(session: Session, project: str) -> str:
    """One line for the note header, so a reader is not misled about coverage."""
    mark = session.get(ObserverWatermark, project)
    if mark is None or mark.swept_at is None:
        return "Coverage: observed live only — not reconciled against git"
    return f"Coverage: observed live, reconciled against git at {mark.swept_at:%H:%M}"
