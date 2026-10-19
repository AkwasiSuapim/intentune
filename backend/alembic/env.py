"""Alembic environment for the Intentune SQLite database.

Migrations use the same engine factory as the application, so connections
get the same SQLite setup (SQLAlchemy-emitted BEGIN, WAL) -- with one
difference: foreign keys are off while migrating, as SQLite's table-rebuild
procedure requires, and PRAGMA foreign_key_check runs before the migration
commits. A violation fails the upgrade and rolls it back.

Because SQLAlchemy emits BEGIN, SQLite DDL is transactional here, and the
whole upgrade runs in one transaction (transactional_ddl=True).
"""

from logging.config import fileConfig

from alembic import context

from src.intentune.persistence.db import configured_database_url, create_database_engine
from src.intentune.persistence.models import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url():
    return config.attributes.get("database_url") or configured_database_url()


def _require_no_foreign_key_violations(connection) -> None:
    violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"Migration left {len(violations)} foreign key violation(s); rolled back")


def run_migrations_offline() -> None:
    """Emit the migration SQL as a script instead of running it."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_database_engine(_database_url(), enforce_foreign_keys=False)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                transactional_ddl=True,
            )

            with context.begin_transaction():
                context.run_migrations()
                _require_no_foreign_key_violations(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
