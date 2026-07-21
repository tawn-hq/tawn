"""SQLAlchemy models for the Tawn memory core.

Vector columns use pgvector's Vector type on Postgres; on SQLite (CI)
the column degrades to Text (no vector ops — integration tests mock embed).
"""

from __future__ import annotations

import datetime
import os

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _vector_column(dims: int):
    """Return a pgvector Vector column, or Text on SQLite / unconfigured."""
    db_url = os.environ.get("TAWN_DB_URL", "")
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
    embedding = _vector_column(1024)
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

    from_entity = relationship(
        "Entity", foreign_keys=[from_entity_id], back_populates="outgoing"
    )
    to_entity = relationship(
        "Entity", foreign_keys=[to_entity_id], back_populates="incoming"
    )


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
