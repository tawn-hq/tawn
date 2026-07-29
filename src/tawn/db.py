"""Database core. One table for Stage 1 (spec §5 snapshots).
No Alembic yet — decision log 2026-07-07: create_all until Stage 3."""

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

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


def migrations_dir() -> Path:
    """Path to the packaged migrations.

    Inside the package, not at the repo root: a repo-root `alembic/` resolves
    fine in an editable checkout and is simply absent from a wheel, so
    `pip install tawn` would silently ship no migrations at all.
    """
    return Path(__file__).parent / "migrations"


def _alembic_cfg(url: str):
    from alembic.config import Config

    here = migrations_dir()
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here))
    # Escape %: ConfigParser interpolates them, and DSNs can carry
    # percent-encoded characters (e.g. a password with '@' → '%40').
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def run_migrations(engine: Engine) -> None:
    """Bring a database up to head.

    Deliberately non-fatal: a migration problem should leave the CLI able to
    start and tell the user what is wrong, not crash on import. `tawn doctor`
    surfaces the current revision.
    """
    from alembic import command

    try:
        cfg = _alembic_cfg(str(engine.url))
        cfg.attributes["connection"] = engine
        command.upgrade(cfg, "head")
    except Exception as exc:  # noqa: BLE001 — see docstring
        import logging

        logging.getLogger(__name__).warning("migrations skipped: %s", exc)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _memory_schema.Base.metadata.create_all(engine)
    _fed_schema.Base.metadata.create_all(engine)
    run_migrations(engine)

    # Fold any legacy audit.log into audit.jsonl. Locked and idempotent, so
    # concurrent CLI / web-daemon / MCP starts are safe. Non-fatal by design:
    # observability must never prevent the process from starting.
    try:
        from tawn.capability.audit import migrate_audit_log
        from tawn.home import tawn_home

        migrate_audit_log(tawn_home())
    except Exception as exc:  # noqa: BLE001 — see comment above
        import logging

        logging.getLogger(__name__).warning("audit migration skipped: %s", exc)


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
