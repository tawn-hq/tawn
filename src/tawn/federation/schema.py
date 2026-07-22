"""FederationRecord — staging table for all ingested AI tool sessions."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class FederationRecord(Base):
    __tablename__ = "federation_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(64), nullable=False)       # adapter name, e.g. "claude-code"
    source_path = Column(Text, nullable=False)         # absolute path to ingested file
    fingerprint = Column(String(16), nullable=False)   # sha256[:16] of file content
    status = Column(String(16), default="pending")     # pending | merged | failed | skipped
    domain = Column(String(64), nullable=True)         # inferred domain, e.g. "work"
    project = Column(String(128), nullable=True)       # inferred project name
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    merged_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("source", "source_path", "fingerprint",
                         name="uq_federation_record"),
    )
