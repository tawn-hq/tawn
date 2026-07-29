"""stage7: enrichment columns and chunk_groups

Adds the columns the resumable enrichment pass writes, plus the
`chunk_groups` roll-up table that heads each feed card.

Note on `chunks.embedding`: autogenerate wants to alter its type here,
because the column is Vector on Postgres and Text on SQLite and the model
resolves that at import time from the local config. It is decided per
installation at table-creation time and must never be migrated — changing
the embedding model is a `tawn compile --rebuild`, not a schema change.
That diff is deliberately omitted.

Revision ID: 09258b784d57
Revises: 87707f354bf5
Create Date: 2026-07-25 00:50:36.931079

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '09258b784d57'
down_revision: Union[str, None] = '87707f354bf5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chunk_groups',
        sa.Column('group_key', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('domain', sa.String(length=64), nullable=True),
        sa.Column('chunk_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('enriched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('enrich_attempts', sa.Integer(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('group_key'),
    )

    # server_default is required, not cosmetic: these are NOT NULL columns
    # being added to tables that already hold rows.
    with op.batch_alter_table('chunks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('title', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('summary', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('enriched_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('enrich_attempts', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('group_key', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('group_label', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_chunks_group_key'), ['group_key'], unique=False)

    with op.batch_alter_table('entity_edges', schema=None) as batch_op:
        batch_op.add_column(sa.Column('weight', sa.Integer(), server_default='1', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('entity_edges', schema=None) as batch_op:
        batch_op.drop_column('weight')

    with op.batch_alter_table('chunks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chunks_group_key'))
        batch_op.drop_column('group_label')
        batch_op.drop_column('group_key')
        batch_op.drop_column('enrich_attempts')
        batch_op.drop_column('enriched_at')
        batch_op.drop_column('summary')
        batch_op.drop_column('title')

    op.drop_table('chunk_groups')
