"""stage7: dimensionless embedding column + per-row embedder provenance

Two changes that belong together, applied in one pass so a 26k-row table is
rewritten once rather than twice.

1. `chunks.embedding` becomes dimensionless. Pinning the column to one
   embedder's width meant switching embed models left config.yaml and the
   column disagreeing, and every subsequent compile died with
   `expected 768 dimensions, not 1536`. pgvector accepts `vector` with no
   width, and Tawn builds no ANN index on this column (only btree on id and
   group_key), so the fixed width bought nothing and cost a class of silent
   breakage.

2. `embed_model` / `embed_dims` record which embedder produced each vector.
   Now that widths can coexist in storage, recall has to restrict itself to
   rows made by the embedder currently in use — distance operators reject
   mixed-width comparisons — and a re-embed needs to know what it replaces.

Existing vectors are preserved; widening to unspecified is not a data change.
`embed_dims` is backfilled from the stored vectors themselves via
`vector_dims()`. `embed_model` is left NULL for pre-existing rows rather than
guessed: the model that wrote them was never recorded, and inventing a name
would make provenance look more certain than it is.

Postgres only — on SQLite the column is Text and there is nothing to alter.

Revision ID: 0003dimensionless
Revises: 09258b784d57
Create Date: 2026-07-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0003dimensionless'
down_revision: Union[str, None] = '09258b784d57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('chunks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('embed_model', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('embed_dims', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_chunks_embed_model'), ['embed_model'], unique=False)

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # USING embedding::vector keeps every existing row.
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector USING embedding::vector")
    # Backfill width from the vectors themselves — factual, not inferred.
    op.execute(
        "UPDATE chunks SET embed_dims = vector_dims(embedding) WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Narrowing back needs a concrete width; take it from the locked
        # config so the downgrade matches this installation.
        from tawn.memory.schema import _locked_embed_dims

        dims = _locked_embed_dims()
        op.execute(
            f"ALTER TABLE chunks ALTER COLUMN embedding TYPE vector({dims}) "
            f"USING embedding::vector({dims})"
        )

    with op.batch_alter_table('chunks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chunks_embed_model'))
        batch_op.drop_column('embed_dims')
        batch_op.drop_column('embed_model')
