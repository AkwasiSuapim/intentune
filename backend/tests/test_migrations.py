"""Alembic migrations: a clean database upgrades, downgrades, matches the ORM records, and fails atomically."""

import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.migrations import alembic_config, upgrade_database
from src.intentune.persistence.models import Base
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork

_INSERT_PROFILE = "INSERT INTO listener_profiles (id, is_default, created_at) VALUES (?, ?, '2026-10-19 12:00:00')"
_FIRST_ID = "3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e"
_SECOND_ID = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"


def _head_revision(database_url):
    return ScriptDirectory.from_config(alembic_config(database_url)).get_current_head()


def _current_revision(database_url):
    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def _table_names(database_url):
    engine = create_database_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _schema_snapshot(database_url):
    """Every table, index, and trigger definition SQLite holds, for before/after comparison."""
    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            return connection.exec_driver_sql(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            ).all()
    finally:
        engine.dispose()


def test_migration_history_has_a_single_head(database_url):
    heads = ScriptDirectory.from_config(alembic_config(database_url)).get_heads()

    assert len(heads) == 1


def test_clean_database_upgrades_to_head(database_url):
    upgrade_database(database_url)

    tables = _table_names(database_url)
    assert _current_revision(database_url) == _head_revision(database_url)
    assert "listener_profiles" in tables
    # Exactly matching the records (no missing or extra tables) is checked by
    # test_migrations_match_the_orm_records.
    assert set(Base.metadata.tables) <= tables


def test_listener_profiles_schema(engine):
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("listener_profiles")}
    primary_key = inspector.get_pk_constraint("listener_profiles")

    assert set(columns) == {"id", "is_default", "created_at"}
    assert [name for name, column in columns.items() if column["nullable"]] == []
    assert primary_key["constrained_columns"] == ["id"]
    assert primary_key["name"] == "pk_listener_profiles"
    assert inspector.get_foreign_keys("listener_profiles") == []


def test_listener_profiles_has_a_unique_index_on_the_default_flag(engine):
    indexes = {index["name"]: index for index in inspect(engine).get_indexes("listener_profiles")}

    index = indexes["uq_listener_profiles_is_default"]
    assert index["unique"]
    assert index["column_names"] == ["is_default"]
    # The index is partial (WHERE is_default = 1). That is verified by behavior:
    # test_database_allows_only_one_default_listener and
    # test_database_allows_several_non_default_listeners.


def test_database_path_with_spaces_and_percent_signs_upgrades(tmp_path):
    directory = tmp_path / "100% local music"
    directory.mkdir()
    database_url = URL.create("sqlite", database=str(directory / "intentune.db"))

    upgrade_database(database_url)

    assert (directory / "intentune.db").is_file()
    assert _current_revision(database_url) == _head_revision(database_url)


def test_upgrading_an_up_to_date_database_is_a_no_op(migrated_database_url):
    before = _schema_snapshot(migrated_database_url)

    upgrade_database(migrated_database_url)

    assert _current_revision(migrated_database_url) == _head_revision(migrated_database_url)
    assert _schema_snapshot(migrated_database_url) == before


def test_downgrade_to_base_removes_the_schema(migrated_database_url):
    command.downgrade(alembic_config(migrated_database_url), "base")

    tables = _table_names(migrated_database_url)
    assert _current_revision(migrated_database_url) is None
    assert "listener_profiles" not in tables
    assert not tables & set(Base.metadata.tables)


def test_upgrade_downgrade_upgrade_round_trip(migrated_database_url):
    config = alembic_config(migrated_database_url)
    first_upgrade = _schema_snapshot(migrated_database_url)

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    assert _current_revision(migrated_database_url) == _head_revision(migrated_database_url)
    assert _schema_snapshot(migrated_database_url) == first_upgrade


def test_migrations_match_the_orm_records(engine):
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert differences == []


def test_database_allows_only_one_default_listener(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(_INSERT_PROFILE, (_FIRST_ID, 1))

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(_INSERT_PROFILE, (_SECOND_ID, 1))

    with engine.begin() as connection:
        connection.exec_driver_sql(_INSERT_PROFILE, (_SECOND_ID, 0))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE listener_profiles SET is_default = 1 WHERE id = ?", (_SECOND_ID,))

    with engine.connect() as connection:
        defaults = connection.exec_driver_sql("SELECT id FROM listener_profiles WHERE is_default = 1").scalars().all()
    assert defaults == [_FIRST_ID]


def test_database_allows_several_non_default_listeners(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(_INSERT_PROFILE, (_FIRST_ID, 0))
        connection.exec_driver_sql(_INSERT_PROFILE, (_SECOND_ID, 0))

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM listener_profiles").scalar() == 2


def test_migrated_database_uses_wal_and_leaves_no_foreign_key_violations(engine):
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []


# --- A failing migration rolls back completely ---------------------------------
#
# B1 makes SQLite DDL transactional (SQLAlchemy emits BEGIN) and runs each
# upgrade as one transaction (transactional_ddl=True in alembic/env.py).
# These tests add a deliberately failing revision on top of the real head. It
# creates a table and rebuilds listener_profiles with an extra column, checks
# that both changes are in effect, then raises. Without transactional DDL the
# changes would survive the failure.

_FAILING_REVISION = "b1_deliberate_failure"

_FAILING_MIGRATION_SOURCE = '''"""Changes the schema, then fails. Used only by tests/test_migrations.py."""
import sqlalchemy as sa
from alembic import op

revision = "b1_deliberate_failure"
down_revision = DOWN_REVISION
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("doomed_table", sa.Column("id", sa.Integer(), primary_key=True))
    with op.batch_alter_table("listener_profiles", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("doomed_column", sa.String(length=10)))

    inspector = sa.inspect(op.get_bind())
    applied = inspector.has_table("doomed_table") and "doomed_column" in {
        column["name"] for column in inspector.get_columns("listener_profiles")
    }
    raise RuntimeError(f"deliberate failure; schema changes applied before it: {applied}")


def downgrade():
    raise NotImplementedError
'''


def _config_with_failing_migration(database_url, tmp_path):
    """An Alembic config whose history is the real migrations plus the failing revision on top."""
    config = alembic_config(database_url)
    script = ScriptDirectory.from_config(config)

    failing_versions = tmp_path / "failing_versions"
    failing_versions.mkdir()
    (failing_versions / f"{_FAILING_REVISION}.py").write_text(
        _FAILING_MIGRATION_SOURCE.replace("DOWN_REVISION", repr(script.get_current_head())),
        encoding="utf-8",
    )
    locations = os.pathsep.join([script.versions, str(failing_versions)])
    config.set_main_option("version_locations", locations.replace("%", "%%"))
    return config


def test_failed_migration_leaves_schema_and_data_unchanged(migrated_database_url, tmp_path):
    engine = create_database_engine(migrated_database_url)
    try:
        listener = ensure_default_listener(SqlAlchemyUnitOfWork(create_session_factory(engine)))
    finally:
        engine.dispose()
    schema_before = _schema_snapshot(migrated_database_url)
    head = _head_revision(migrated_database_url)

    with pytest.raises(RuntimeError, match="schema changes applied before it: True"):
        command.upgrade(_config_with_failing_migration(migrated_database_url, tmp_path), _FAILING_REVISION)

    assert _schema_snapshot(migrated_database_url) == schema_before
    assert _current_revision(migrated_database_url) == head
    engine = create_database_engine(migrated_database_url)
    try:
        with SqlAlchemyUnitOfWork(create_session_factory(engine)) as unit_of_work:
            assert unit_of_work.listener_profiles.get_default() == listener
    finally:
        engine.dispose()


def test_failed_upgrade_from_empty_rolls_back_every_revision_in_it(database_url, tmp_path):
    schema_before = _schema_snapshot(database_url)

    with pytest.raises(RuntimeError, match="schema changes applied before it: True"):
        command.upgrade(_config_with_failing_migration(database_url, tmp_path), _FAILING_REVISION)

    assert schema_before == []
    assert _schema_snapshot(database_url) == schema_before
    assert _current_revision(database_url) is None
