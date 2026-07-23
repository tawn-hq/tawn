"""Database core. One table for Stage 1 (spec §5 snapshots).
No Alembic yet — decision log 2026-07-07: create_all until Stage 3."""

from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool, StaticPool

from tawn.config import settings
import tawn.memory.schema as _memory_schema  # registers memory models with their own Base
import tawn.federation.schema as _fed_schema  # registers FederationRecord


class Base(DeclarativeBase):
    pass


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(32), index=True)
    asof: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    state_json: Mapped[str] = mapped_column(Text)


Index("ix_snapshots_domain_asof", Snapshot.domain, Snapshot.asof)


def make_engine(url: str | None = None, *, pooled: bool = False) -> Engine:
    """Create a SQLAlchemy engine.

    pooled=False (default): NullPool — each connection is acquired and
    immediately released after use. Right for one-shot CLI commands and
    background scripts where a held connection wastes RAM.

    pooled=True: small pool (size 2, max_overflow 1) for the web server
    where multiple requests share a long-lived process.

    SQLite :memory: always uses StaticPool so the same in-memory DB is
    reused across checkouts (needed for tests).
    """
    db_url = url or settings().db_url
    if ":memory:" in db_url:
        # StaticPool: single connection, reused — required for in-memory SQLite
        return create_engine(
            db_url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    if not pooled:
        return create_engine(db_url, poolclass=NullPool)
    return create_engine(
        db_url,
        pool_size=2,
        max_overflow=1,
        pool_recycle=300,   # release idle connections after 5 min
        pool_pre_ping=True, # discard stale connections before use
    )


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _memory_schema.Base.metadata.create_all(engine)
    _fed_schema.Base.metadata.create_all(engine)
    _migrate_columns(engine)


def _migrate_columns(engine: Engine) -> None:
    """Add new columns to existing tables that predate them."""
    _new_cols = [
        ("federation_records", "domain", "VARCHAR(64)"),
        ("federation_records", "project", "VARCHAR(128)"),
    ]
    with engine.connect() as conn:
        from sqlalchemy import text
        for table, col, col_type in _new_cols:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}"
                ))
                conn.commit()
            except Exception:
                conn.rollback()


@contextmanager
def session(engine: Engine):
    with Session(engine) as s:
        yield s


_init_done = False


def get_session():
    """FastAPI dependency — yields a Session bound to the default engine."""
    global _init_done
    engine = make_engine()
    if not _init_done:
        init_db(engine)
        _init_done = True
    with Session(engine) as s:
        yield s
