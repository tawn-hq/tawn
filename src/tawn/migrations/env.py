"""Alembic environment for Tawn.

Three declarative bases share one database (core, memory, federation), so
`target_metadata` is a list — autogenerate walks all three.
"""

from alembic import context
from sqlalchemy import engine_from_config, pool

from tawn.db import Base as _core_base
from tawn.federation import schema as _fed_schema
from tawn.memory import schema as _memory_schema

config = context.config

target_metadata = [
    _core_base.metadata,
    _memory_schema.Base.metadata,
    _fed_schema.Base.metadata,
]


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        # render_as_batch: SQLite cannot ALTER most things in place, so
        # batch mode rebuilds the table instead. Harmless on Postgres.
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
