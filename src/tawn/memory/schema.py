"""SQLAlchemy models for the Tawn memory core.

Vector columns use pgvector's Vector type on Postgres; on SQLite (CI)
the column degrades to Text (no vector ops — integration tests mock embed).
"""

from __future__ import annotations

import datetime
import os

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    Numeric,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


_DEFAULT_EMBED_DIMS = 768


def _locked_embed_dims() -> int:
    """Read embed_dims locked in ~/.tawn/config.yaml, or fall back to default."""
    from tawn.home import tawn_home
    cfg_path = tawn_home() / "config.yaml"
    if cfg_path.exists():
        try:
            import yaml
            cfg = yaml.safe_load(cfg_path.read_text()) or {}
            dims = cfg.get("embed_dims")
            if dims:
                return int(dims)
        except Exception:
            pass
    return _DEFAULT_EMBED_DIMS


def _vector_column(dims: int | None = None):
    """Return a pgvector Vector column, or Text on SQLite / unconfigured.

    Deliberately *dimensionless*. Pinning the column to one embedder's width
    meant switching models left the config and the column disagreeing, and
    every subsequent compile died on `expected 768 dimensions, not 1536`.
    pgvector accepts `vector` with no width, and Tawn builds no ANN index on
    this column (only btree on id and group_key), so the fixed width bought
    nothing and cost a whole class of breakage.

    Rows of differing widths can coexist in storage, but distance operators
    reject mixed comparisons — so changing embedder still requires a
    re-embed, which `PUT /api/models/embed` enforces.
    """
    from tawn.config import settings as _settings
    db_url = os.environ.get("TAWN_DB_URL") or _settings().db_url
    if "postgresql" in db_url:
        try:
            from pgvector.sqlalchemy import Vector
            return Column(Vector(dims), nullable=True)
        except ImportError:
            pass
    return Column(Text, nullable=True)


class Base(DeclarativeBase):
    pass


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(64), nullable=True)
    source_path = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = _vector_column()
    content_hash = Column(String(16), nullable=False)
    priority_tier = Column(SmallInteger, nullable=False, default=3)
    asof = Column(DateTime(timezone=True), nullable=False)
    ttl_days = Column(Integer, nullable=True)
    stale = Column(Boolean, nullable=False, default=False)
    compiled_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.datetime.utcnow,
    )

    # ── enrichment (Stage 7) ──────────────────────────────────────────────
    # Written by the resumable pass in compiler/enrich.py, not by compile.
    # `enrich_attempts` caps retries: without it a chunk the model reliably
    # fails to parse would be reselected every 30 minutes forever.
    title = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    enriched_at = Column(DateTime(timezone=True), nullable=True)
    enrich_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    group_key = Column(Text, nullable=True, index=True)
    group_label = Column(Text, nullable=True)

    # Which embedder produced `embedding`. Recorded per row because the
    # column is dimensionless: vectors of different widths can coexist, but
    # distance operators reject mixed comparisons, so recall must restrict
    # itself to rows made by the embedder currently in use — and a re-embed
    # needs to know what it is replacing.
    embed_model = Column(String(64), nullable=True, index=True)
    embed_dims = Column(Integer, nullable=True)


class Entity(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canonical = Column(Text, nullable=False, unique=True)
    domain = Column(String(64), nullable=True)
    first_seen = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.datetime.utcnow,
    )
    last_updated = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.datetime.utcnow,
    )
    confidence = Column(String(16), nullable=False, default="medium")
    source_path = Column(Text, nullable=True)

    outgoing = relationship(
        "EntityEdge",
        foreign_keys="EntityEdge.from_entity_id",
        back_populates="from_entity",
        cascade="all, delete-orphan",
    )
    incoming = relationship(
        "EntityEdge",
        foreign_keys="EntityEdge.to_entity_id",
        back_populates="to_entity",
        cascade="all, delete-orphan",
    )


class EntityEdge(Base):
    __tablename__ = "entity_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"))
    to_entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"))
    relation = Column(Text, nullable=False)
    confidence = Column(String(16), nullable=True)
    source_path = Column(Text, nullable=True)
    # How many times this pairing was seen. Drives edge thickness in the
    # graph and separates a one-off mention from a real association.
    weight = Column(Integer, nullable=False, default=1, server_default="1")

    from_entity = relationship(
        "Entity", foreign_keys=[from_entity_id], back_populates="outgoing"
    )
    to_entity = relationship(
        "Entity", foreign_keys=[to_entity_id], back_populates="incoming"
    )


class ChunkGroup(Base):
    """Roll-up header for a feed card. One row per distinct Chunk.group_key.

    Chunks are not the display unit — 26k rows is not a feed anyone reads.
    A conversation or document is one card, and its title/summary come from
    a single roll-up model call over its members' summaries.
    """

    __tablename__ = "chunk_groups"

    group_key = Column(Text, primary_key=True)
    title = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    domain = Column(String(64), nullable=True)
    chunk_count = Column(Integer, nullable=False, default=0, server_default="0")
    enriched_at = Column(DateTime(timezone=True), nullable=True)
    enrich_attempts = Column(Integer, nullable=False, default=0, server_default="0")


class FileState(Base):
    __tablename__ = "file_state"

    path = Column(Text, primary_key=True)
    mtime = Column(Float, nullable=False)
    content_hash = Column(String(64), nullable=False)
    compiled_at = Column(DateTime(timezone=True), nullable=False)


class CompileLog(Base):
    __tablename__ = "compile_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    files_processed = Column(Integer, nullable=True)
    chunks_added = Column(Integer, nullable=True)
    chunks_removed = Column(Integer, nullable=True)
    entities_resolved = Column(Integer, nullable=True)
    ok = Column(Boolean, nullable=True)
    error = Column(Text, nullable=True)


class ModelCallRollup(Base):
    """Daily aggregates of model calls — a derived cache over ledger.jsonl.

    The file is the source of truth; this table holds no fact that does not
    originate there, so any disagreement is resolved by recomputing it rather
    than reconciling two peers. Recording every embed call takes the ledger
    from dozens of entries to ~12,000 per rebuild, which the UI must not read
    line by line.
    """

    __tablename__ = "model_call_rollups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(Date, nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    model = Column(String(128), nullable=False)
    caller = Column(String(16), nullable=False, default="system")
    operation = Column(String(32), nullable=False, default="")
    domain = Column(String(64), nullable=True)
    calls = Column(Integer, nullable=False, default=0)
    tokens_in = Column(Integer, nullable=False, default=0)
    tokens_out = Column(Integer, nullable=False, default=0)
    # Numeric, never float: money summed through binary floating point drifts,
    # and a cost dashboard that disagrees with its own source is worse than none.
    cost_usd = Column(Numeric(18, 8), nullable=False, default=0)
    # Lets a total state its own incompleteness instead of understating.
    unpriced_calls = Column(Integer, nullable=False, default=0)


class ObserverSession(Base):
    """One project's window of contiguous activity.

    Opened by the first event for a project with no open session, closed by a
    commit, by idle timeout, or by an explicit review. `note_state` and
    `note_attempts` give note-writing the same resumable-and-bounded contract
    enrichment uses: a note that cannot be written is retried on later sweeps
    and eventually gives up rather than retrying forever.
    """

    __tablename__ = "observer_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project = Column(String(128), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(String(16), nullable=True)  # commit | idle | manual
    event_count = Column(Integer, nullable=False, default=0, server_default="0")
    note_path = Column(Text, nullable=True)
    # open | pending_note | written | unanalysed | failed
    note_state = Column(
        String(16), nullable=False, default="open", server_default="open"
    )
    note_attempts = Column(Integer, nullable=False, default=0, server_default="0")


class ObservedEvent(Base):
    """One observed change.

    Deliberately holds no file content — only path, kind and line deltas.
    Storing diffs would make Tawn an unversioned second copy of the user's
    source that outlives deletion. Review composition reads the file through
    the normal grant check instead.
    """

    __tablename__ = "observed_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer, ForeignKey("observer_sessions.id", ondelete="CASCADE"), index=True
    )
    project = Column(String(128), nullable=False, index=True)
    path = Column(Text, nullable=False)
    kind = Column(String(16), nullable=False)  # added|modified|deleted|commit
    lines_added = Column(Integer, nullable=False, default=0, server_default="0")
    lines_removed = Column(Integer, nullable=False, default=0, server_default="0")
    actor = Column(
        String(64), nullable=False, default="unknown", server_default="unknown"
    )
    confidence = Column(String(8), nullable=False, default="low", server_default="low")
    basis = Column(String(16), nullable=False, default="none", server_default="none")
    ts = Column(DateTime(timezone=True), nullable=False)


class ObserverWatermark(Base):
    """How far the git sweep has reconciled one project.

    The watcher only knows what inotify told it while it was running, which
    excludes the ~15s the recursive watch takes to arm, any period the daemon was
    stopped, and events dropped under queue overflow. The sweep reconciles that
    record against git, and this row is what keeps a second sweep cheap.

    `last_commit` bounds commit reconciliation to `last_commit..HEAD`.
    `tree_digest` is a hash over the sorted dirty-set `(path, size, mtime_ns)`, so
    an unchanged working tree costs one comparison rather than one query per file.
    """

    __tablename__ = "observer_watermark"

    project = Column(String(128), primary_key=True)
    last_commit = Column(String(64), nullable=True)
    tree_digest = Column(String(64), nullable=True)
    swept_at = Column(DateTime(timezone=True), nullable=False)


class FileSnapshot(Base):
    """Last-known state of one file, for change detection without git.

    The same trick an editor or a backup tool uses: `(size, mtime_ns)` is a cheap
    gate, and only when that differs is the content hashed to confirm a real
    change. That distinction matters — a `touch`, a checkout of identical content,
    or a formatter that rewrites the same bytes all move mtime without changing
    anything, and recording those as edits would fill the log with noise.

    `digest` is of content; `lines` lets a net line delta be reported without
    keeping a copy of the file, which `ObservedEvent` deliberately never does.

    Distinct from `FileState`, which serves the compiler: that one is keyed on
    path alone and tracks what has been *ingested*, this one is keyed per project
    and tracks what has been *observed*. Sharing a table would couple the
    observer's change detection to compile scheduling.
    """

    __tablename__ = "file_snapshots"

    project = Column(String(128), primary_key=True)
    path = Column(Text, primary_key=True)
    size = Column(Integer, nullable=False, default=0)
    mtime_ns = Column(BigInteger, nullable=False, default=0)
    digest = Column(String(64), nullable=True)
    lines = Column(Integer, nullable=False, default=0)
    seen_at = Column(DateTime(timezone=True), nullable=False)


class LedgerWatermark(Base):
    """How far the reconciler has read into a ledger file."""

    __tablename__ = "ledger_watermark"

    path = Column(Text, primary_key=True)
    byte_offset = Column(Integer, nullable=False, default=0)
    entries_seen = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow
    )
