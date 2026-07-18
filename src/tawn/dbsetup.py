"""Postgres bootstrap ladder (`tawn db setup`).

Detect, then do only what's missing. Tawn can create the *database*
itself when the server is up and peer auth works; installing the
*server* needs sudo, so we print exact commands instead of guessing.
"""

from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.engine import make_url

INSTALL_HINTS = """\
postgres server not reachable. Install and start it, then re-run:

  Ubuntu/Debian:  sudo apt install -y postgresql && sudo systemctl enable --now postgresql
  Fedora:         sudo dnf install -y postgresql-server && sudo postgresql-setup --initdb && sudo systemctl enable --now postgresql
  macOS (brew):   brew install postgresql@16 && brew services start postgresql@16
"""


@dataclass
class DbStatus:
    server_up: bool
    db_exists: bool
    can_connect: bool
    detail: str = ""


def probe(url: str) -> DbStatus:
    """Can we connect to the target database right now?

    NullPool: a probe must not hold a connection open afterwards
    (a lingering pool blocks DROP/ALTER DATABASE).
    """
    try:
        engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
        with engine.connect():
            return DbStatus(server_up=True, db_exists=True, can_connect=True)
    except sa.exc.OperationalError as e:
        msg = str(e.orig).lower() if e.orig else str(e).lower()
        if "does not exist" in msg:
            return DbStatus(server_up=True, db_exists=False, can_connect=False, detail=msg)
        return DbStatus(server_up=False, db_exists=False, can_connect=False, detail=msg)


def ensure_database(url: str) -> DbStatus:
    """Create the target database if the server is up but the db is missing."""
    st = probe(url)
    if st.can_connect or not st.server_up:
        return st
    u = make_url(url)
    admin_url = u.set(database="postgres")
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=sa.pool.NullPool)
    with admin.connect() as c:
        c.execute(sa.text(f'CREATE DATABASE "{u.database}"'))
    return probe(url)
