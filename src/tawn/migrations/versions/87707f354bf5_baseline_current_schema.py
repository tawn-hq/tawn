"""baseline: current schema

Establishes the version marker for databases that predate Alembic.

Idempotent by design. Existing installs already have every one of these
tables (they were created by `create_all`), so a plain `create_table` would
raise "table already exists" and abort the upgrade — leaving later revisions
unapplied. Each table is therefore created only when absent, which makes this
revision a no-op stamp on an existing database and a full schema build on a
fresh one.

Revision ID: 87707f354bf5
Revises:
Create Date: 2026-07-25 00:39:45.659694

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '87707f354bf5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _embedding_column() -> sa.Column:
    """Vector on Postgres, Text elsewhere.

    Dimensions are locked per-installation in config.yaml (see
    `memory.schema._locked_embed_dims`), so this must be read at migration
    time rather than baked into the revision.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        try:
            from pgvector.sqlalchemy import Vector

            from tawn.memory.schema import _locked_embed_dims

            return sa.Column('embedding', Vector(_locked_embed_dims()), nullable=True)
        except ImportError:
            pass
    return sa.Column('embedding', sa.Text(), nullable=True)


def upgrade() -> None:
    existing = _existing()

    if 'snapshots' not in existing:
        op.create_table(
            'snapshots',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('domain', sa.String(length=32), nullable=False),
            sa.Column('asof', sa.DateTime(timezone=True), nullable=False),
            sa.Column('state_json', sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_snapshots_asof'), 'snapshots', ['asof'], unique=False)
        op.create_index(op.f('ix_snapshots_domain'), 'snapshots', ['domain'], unique=False)
        op.create_index('ix_snapshots_domain_asof', 'snapshots', ['domain', 'asof'], unique=False)

    if 'chunks' not in existing:
        op.create_table(
            'chunks',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('domain', sa.String(length=64), nullable=True),
            sa.Column('source_path', sa.Text(), nullable=False),
            sa.Column('chunk_index', sa.Integer(), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            _embedding_column(),
            sa.Column('content_hash', sa.String(length=16), nullable=False),
            sa.Column('priority_tier', sa.SmallInteger(), nullable=False),
            sa.Column('asof', sa.DateTime(timezone=True), nullable=False),
            sa.Column('ttl_days', sa.Integer(), nullable=True),
            sa.Column('stale', sa.Boolean(), nullable=False),
            sa.Column('compiled_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )

    if 'compile_log' not in existing:
        op.create_table(
            'compile_log',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('files_processed', sa.Integer(), nullable=True),
            sa.Column('chunks_added', sa.Integer(), nullable=True),
            sa.Column('chunks_removed', sa.Integer(), nullable=True),
            sa.Column('entities_resolved', sa.Integer(), nullable=True),
            sa.Column('ok', sa.Boolean(), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )

    if 'entities' not in existing:
        op.create_table(
            'entities',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('canonical', sa.Text(), nullable=False),
            sa.Column('domain', sa.String(length=64), nullable=True),
            sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
            sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
            sa.Column('confidence', sa.String(length=16), nullable=False),
            sa.Column('source_path', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('canonical'),
        )

    if 'file_state' not in existing:
        op.create_table(
            'file_state',
            sa.Column('path', sa.Text(), nullable=False),
            sa.Column('mtime', sa.Float(), nullable=False),
            sa.Column('content_hash', sa.String(length=64), nullable=False),
            sa.Column('compiled_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('path'),
        )

    if 'entity_edges' not in existing:
        op.create_table(
            'entity_edges',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('from_entity_id', sa.Integer(), nullable=True),
            sa.Column('to_entity_id', sa.Integer(), nullable=True),
            sa.Column('relation', sa.Text(), nullable=False),
            sa.Column('confidence', sa.String(length=16), nullable=True),
            sa.Column('source_path', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['from_entity_id'], ['entities.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['to_entity_id'], ['entities.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    if 'federation_records' not in existing:
        # `domain` and `project` are included here rather than as a follow-up
        # ALTER: they were previously applied by the hand-rolled
        # `db._migrate_columns()`, which this revision replaces.
        op.create_table(
            'federation_records',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('source', sa.String(length=64), nullable=False),
            sa.Column('source_path', sa.Text(), nullable=False),
            sa.Column('fingerprint', sa.String(length=16), nullable=False),
            sa.Column('status', sa.String(length=16), nullable=True),
            sa.Column('domain', sa.String(length=64), nullable=True),
            sa.Column('project', sa.String(length=128), nullable=True),
            sa.Column(
                'ingested_at', sa.DateTime(timezone=True),
                server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True,
            ),
            sa.Column('merged_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('source', 'source_path', 'fingerprint', name='uq_federation_record'),
        )
    else:
        # Pre-Alembic installs may lack these two — the old helper added them
        # at runtime and is now gone.
        cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('federation_records')}
        if 'domain' not in cols:
            op.add_column('federation_records', sa.Column('domain', sa.String(length=64), nullable=True))
        if 'project' not in cols:
            op.add_column('federation_records', sa.Column('project', sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_table('federation_records')
    op.drop_table('entity_edges')
    op.drop_table('file_state')
    op.drop_table('entities')
    op.drop_table('compile_log')
    op.drop_table('chunks')
    op.drop_index('ix_snapshots_domain_asof', table_name='snapshots')
    op.drop_index(op.f('ix_snapshots_domain'), table_name='snapshots')
    op.drop_index(op.f('ix_snapshots_asof'), table_name='snapshots')
    op.drop_table('snapshots')
