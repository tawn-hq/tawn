"""observer git sweep — observer_watermark

Revision ID: b7e2c1f4a903
Revises: a1c4f9b02e77
Create Date: 2026-07-31

Hand-written for the same reason as the stage 9 revision: autogenerate in this
repo injects a `pgvector...VECTOR(dim=…)` reference with no import, and one table
with no vector columns is cheaper to state than to generate and repair.
"""

from alembic import op
import sqlalchemy as sa

revision = "b7e2c1f4a903"
down_revision = "a1c4f9b02e77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observer_watermark",
        sa.Column("project", sa.String(length=128), primary_key=True),
        sa.Column("last_commit", sa.String(length=64), nullable=True),
        sa.Column("tree_digest", sa.String(length=64), nullable=True),
        sa.Column("swept_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "file_snapshots",
        sa.Column("project", sa.String(length=128), primary_key=True),
        sa.Column("path", sa.Text(), primary_key=True),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("digest", sa.String(length=64), nullable=True),
        sa.Column("lines", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("file_snapshots")
    op.drop_table("observer_watermark")
