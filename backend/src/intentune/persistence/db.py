"""Database configuration: where the SQLite file lives and how connections behave.

Prototype 1 uses synchronous SQLAlchemy over SQLite (D22). This module is the
one place that decides:

- Which database to open. `DATABASE_URL` from the process environment, or
  backend/data/intentune.db when it is unset. A relative SQLite path is
  resolved against the backend root (backend/), the same way the CSV
  adapter resolves data/songs.csv, so the database location does not depend
  on the working directory. The backend/.env file is not loaded yet.
- How every connection is configured:
  * foreign keys are enforced (SQLite leaves them off by default);
  * file databases use write-ahead logging (WAL), so readers do not block
    the writer -- B3's background worker will write while the API reads;
  * SQLAlchemy, not the sqlite3 driver, emits BEGIN. Python 3.11's sqlite3
    driver skips BEGIN for SELECT and DDL statements, which makes schema
    changes non-transactional and breaks SAVEPOINT. Emitting BEGIN ourselves
    is the approach SQLAlchemy documents for all Python versions.

Only SQLite is accepted. PostgreSQL is future work (D22).
"""

import os
from pathlib import Path
from typing import Optional, Union

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "intentune.db"
DATABASE_URL_ENV_VAR = "DATABASE_URL"


def _is_file_database(url: URL) -> bool:
    database = url.database
    return bool(database) and database != ":memory:" and not database.startswith("file:")


def resolve_database_url(raw_url: Optional[str]) -> URL:
    """Turn a configured database URL into the URL Intentune actually opens.

    None or blank means the default file, backend/data/intentune.db. A
    relative SQLite file path is made absolute against the backend root.
    In-memory and `file:` URI databases are returned unchanged.

    Returns a URL object rather than a string: a rendered SQLite URL
    percent-encodes the path, and re-parsing it is avoidable work.
    """
    if raw_url is None or not raw_url.strip():
        return URL.create("sqlite", database=str(DEFAULT_DATABASE_PATH))

    url = make_url(raw_url.strip())
    if url.get_backend_name() != "sqlite":
        raise ValueError(f"Prototype 1 supports only SQLite databases, not {url.get_backend_name()!r}")

    if _is_file_database(url):
        path = Path(url.database)
        if not path.is_absolute():
            path = (BACKEND_ROOT / path).resolve()
        url = url.set(database=str(path))
    return url


def configured_database_url() -> URL:
    """The database URL from the `DATABASE_URL` environment variable, resolved."""
    return resolve_database_url(os.environ.get(DATABASE_URL_ENV_VAR))


def create_database_engine(database_url: Union[str, URL], *, enforce_foreign_keys: bool = True) -> Engine:
    """Create an engine whose connections are configured as described in the module docstring.

    Migrations pass enforce_foreign_keys=False: SQLite's documented procedure
    for rebuilding a table (which Alembic's batch mode does) requires foreign
    keys to be off, then checked with PRAGMA foreign_key_check afterwards.
    Everything else keeps the default.
    """
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError(f"Prototype 1 supports only SQLite databases, not {url.get_backend_name()!r}")

    engine = create_engine(url)
    use_wal = _is_file_database(url)
    foreign_keys = "ON" if enforce_foreign_keys else "OFF"

    @event.listens_for(engine, "connect")
    def _configure_connection(dbapi_connection, _connection_record) -> None:
        # Stop the driver from managing transactions; _begin_transaction does it.
        # PRAGMAs below then run outside any transaction, which they require.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA foreign_keys = {foreign_keys}")
            if use_wal:
                cursor.execute("PRAGMA journal_mode = WAL")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def _begin_transaction(connection) -> None:
        connection.exec_driver_sql("BEGIN")

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """A factory for ORM sessions bound to this engine. Units of work open one per transaction."""
    return sessionmaker(bind=engine)
