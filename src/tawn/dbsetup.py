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
  Windows:        install from postgresql.org/download/windows, set a password for
                   the postgres user, then set TAWN_DB_URL to match — e.g.
                   postgresql+psycopg://postgres:yourpassword@localhost/tawn
"""


@dataclass
class DbStatus:
    server_up: bool
    db_exists: bool
    can_connect: bool
    detail: str = ""
    # Whether pgvector is available. Without it embeddings cannot be stored
    # and recall degrades to keyword search.
    vector_ready: bool = False
    vector_detail: str = ""


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


PGVECTOR_HINTS = """\
pgvector extension not available — semantic search will fall back to keyword
matching until it is installed. Install the extension package, then re-run
`tawn db setup`:

  Ubuntu/Debian:  sudo apt install -y postgresql-16-pgvector
  Fedora:         sudo dnf install -y pgvector
  macOS (brew):   brew install pgvector
  Docker:         use the pgvector/pgvector:pg16 image
"""


def ensure_vector_extension(url: str) -> tuple[bool, str]:
    """Enable pgvector on the target database. Returns (enabled, detail).

    Creating the database is not enough: without this extension the embedding
    column cannot exist, and recall silently degrades to keyword search — the
    kind of quiet downgrade a person only notices when results feel wrong.
    Requires the server-side package, which needs root to install, so a
    failure here is reported rather than raised.
    """
    try:
        engine = sa.create_engine(url, isolation_level="AUTOCOMMIT", poolclass=sa.pool.NullPool)
        with engine.connect() as c:
            c.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        return True, "pgvector enabled"
    except Exception as exc:  # noqa: BLE001 — surfaced to the user, not raised
        return False, str(exc).split("\n")[0]


def ensure_database(url: str) -> DbStatus:
    """Create the target database if the server is up but the db is missing.

    Also enables pgvector, since a database without it cannot store
    embeddings and recall quietly falls back to keyword matching.
    """
    st = probe(url)
    if not st.server_up:
        return st

    if not st.can_connect:
        u = make_url(url)
        admin_url = u.set(database="postgres")
        admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=sa.pool.NullPool)
        with admin.connect() as c:
            c.execute(sa.text(f'CREATE DATABASE "{u.database}"'))
        st = probe(url)

    if st.can_connect:
        ok, detail = ensure_vector_extension(url)
        st.vector_ready = ok
        st.vector_detail = detail
    return st
