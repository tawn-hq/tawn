"""Database core. One table for Stage 1 (spec §5 snapshots).
No Alembic yet — decision log 2026-07-07: create_all until Stage 3."""

from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from tawn.config import settings


class Base(DeclarativeBase):
    pass


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(32), index=True)
    asof: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    state_json: Mapped[str] = mapped_column(Text)


Index("ix_snapshots_domain_asof", Snapshot.domain, Snapshot.asof)


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or settings().db_url)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session(engine: Engine):
    with Session(engine) as s:
        yield s
