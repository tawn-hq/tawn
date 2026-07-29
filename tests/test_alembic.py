import sqlalchemy as sa
from alembic import command

from tawn.db import _alembic_cfg, run_migrations


def test_migrations_apply_to_fresh_db(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path/'fresh.db'}"
    command.upgrade(_alembic_cfg(url), "head")
    insp = sa.inspect(sa.create_engine(url))
    assert "chunks" in insp.get_table_names()
    assert "entities" in insp.get_table_names()


def test_migrations_match_create_all(tmp_path):
    """Alembic head and create_all must produce the same tables."""
    from tawn.db import init_db

    mig_url = f"sqlite+pysqlite:///{tmp_path/'mig.db'}"
    command.upgrade(_alembic_cfg(mig_url), "head")
    mig_tables = set(sa.inspect(sa.create_engine(mig_url)).get_table_names())

    ca_engine = sa.create_engine(f"sqlite+pysqlite:///{tmp_path/'ca.db'}")
    init_db(ca_engine)
    ca_tables = set(sa.inspect(ca_engine).get_table_names())

    assert mig_tables - {"alembic_version"} == ca_tables - {"alembic_version"}


def test_migration_dir_ships_inside_the_package():
    """Wheels must carry the migrations — repo-root paths break pip installs."""
    from pathlib import Path

    import tawn

    pkg_root = Path(tawn.__file__).parent
    assert (pkg_root / "migrations" / "env.py").is_file()
    assert (pkg_root / "migrations" / "alembic.ini").is_file()
    assert (pkg_root / "migrations" / "versions").is_dir()


def test_run_migrations_is_non_fatal_on_bad_url(caplog):
    """A migration failure must not stop the process from starting."""
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    engine.url = engine.url.set(database="/nonexistent-dir/x.db")
    # Should return, not raise.
    run_migrations(sa.create_engine("sqlite+pysqlite:////nonexistent-dir/x.db"))
