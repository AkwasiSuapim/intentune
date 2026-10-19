"""Database configuration: URL resolution, connection setup, and the UTC column type."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, inspect, insert, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, StatementError

from src.intentune.persistence.db import (
    BACKEND_ROOT,
    DEFAULT_DATABASE_PATH,
    configured_database_url,
    create_database_engine,
    resolve_database_url,
)
from src.intentune.persistence.models import UtcDateTime


def _database_path(url):
    return Path(make_url(url).database)


@pytest.fixture
def raw_engine(database_url):
    """An engine on an empty, unmigrated database."""
    engine = create_database_engine(database_url)
    yield engine
    engine.dispose()


# --- URL resolution ------------------------------------------------------


def test_backend_root_is_the_backend_directory():
    assert (BACKEND_ROOT / "requirements.txt").is_file()
    assert (BACKEND_ROOT / "alembic.ini").is_file()


def test_default_database_is_backend_data_intentune_db():
    assert DEFAULT_DATABASE_PATH == BACKEND_ROOT / "data" / "intentune.db"


@pytest.mark.parametrize("unset", [None, "", "   "])
def test_unset_url_resolves_to_the_default_database(unset):
    assert _database_path(resolve_database_url(unset)) == DEFAULT_DATABASE_PATH


def test_relative_sqlite_path_resolves_against_backend_root_not_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    resolved = resolve_database_url("sqlite:///./data/intentune.db")

    assert _database_path(resolved) == DEFAULT_DATABASE_PATH


def test_env_example_database_url_resolves_to_the_default_database():
    env_example = (BACKEND_ROOT / ".env.example").read_text(encoding="utf-8")
    lines = [line for line in env_example.splitlines() if line.startswith("DATABASE_URL=")]

    assert len(lines) == 1
    assert _database_path(resolve_database_url(lines[0].split("=", 1)[1])) == DEFAULT_DATABASE_PATH


def test_absolute_sqlite_path_is_kept(tmp_path):
    absolute = tmp_path / "elsewhere.db"

    assert _database_path(resolve_database_url(f"sqlite:///{absolute.as_posix()}")) == absolute


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:"])
def test_in_memory_url_is_kept(url):
    assert resolve_database_url(url) == make_url(url)


@pytest.mark.parametrize("url", ["postgresql://user:pass@localhost/intentune", "mysql://localhost/intentune"])
def test_non_sqlite_url_is_rejected(url):
    with pytest.raises(ValueError, match="only SQLite"):
        resolve_database_url(url)


def test_non_sqlite_engine_is_rejected():
    with pytest.raises(ValueError, match="only SQLite"):
        create_database_engine("postgresql://user:pass@localhost/intentune")


def test_configured_url_reads_the_database_url_environment_variable(tmp_path, monkeypatch):
    target = tmp_path / "from-env.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{target.as_posix()}")

    assert _database_path(configured_database_url()) == target


def test_configured_url_defaults_when_environment_variable_is_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert _database_path(configured_database_url()) == DEFAULT_DATABASE_PATH


# --- Connection setup ----------------------------------------------------


def test_connections_enforce_foreign_keys(raw_engine):
    with raw_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_foreign_key_violation_is_rejected(raw_engine):
    metadata = MetaData()
    Table("parent", metadata, Column("id", Integer, primary_key=True))
    child = Table("child", metadata, Column("id", Integer, primary_key=True), Column("parent_id", ForeignKey("parent.id")))
    metadata.create_all(raw_engine)

    with pytest.raises(IntegrityError):
        with raw_engine.begin() as connection:
            connection.execute(insert(child).values(id=1, parent_id=999))

    with raw_engine.connect() as connection:
        assert connection.execute(select(child)).all() == []


def test_migration_engine_can_turn_foreign_keys_off(database_url):
    engine = create_database_engine(database_url, enforce_foreign_keys=False)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
    finally:
        engine.dispose()


def test_file_database_uses_wal_journal_mode(raw_engine):
    with raw_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"


def test_in_memory_database_works_without_wal():
    engine = create_database_engine("sqlite://")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "memory"
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    finally:
        engine.dispose()


def test_schema_changes_are_transactional(raw_engine):
    connection = raw_engine.connect()
    try:
        transaction = connection.begin()
        connection.exec_driver_sql("CREATE TABLE scratch (id INTEGER PRIMARY KEY)")
        transaction.rollback()
    finally:
        connection.close()

    assert "scratch" not in inspect(raw_engine).get_table_names()


def test_rolled_back_insert_is_discarded(raw_engine):
    metadata = MetaData()
    items = Table("items", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(raw_engine)

    connection = raw_engine.connect()
    try:
        transaction = connection.begin()
        connection.execute(insert(items).values(id=1))
        transaction.rollback()
    finally:
        connection.close()

    with raw_engine.connect() as connection:
        assert connection.execute(select(items)).all() == []


# --- UtcDateTime ----------------------------------------------------------


@pytest.fixture
def events_table(raw_engine):
    metadata = MetaData()
    table = Table("events", metadata, Column("id", Integer, primary_key=True), Column("at", UtcDateTime))
    metadata.create_all(raw_engine)
    return table


def _store_and_load(engine, table, value):
    with engine.begin() as connection:
        connection.execute(insert(table).values(id=1, at=value))
    with engine.connect() as connection:
        return connection.execute(select(table.c.at)).scalar_one()


def test_utc_datetime_round_trips_as_aware_utc(raw_engine, events_table):
    moment = datetime(2026, 10, 19, 12, 30, 15, 123456, tzinfo=timezone.utc)

    loaded = _store_and_load(raw_engine, events_table, moment)

    assert loaded == moment
    assert loaded.tzinfo == timezone.utc


def test_utc_datetime_converts_other_offsets_to_utc(raw_engine, events_table):
    five_hours_behind = timezone(timedelta(hours=-5))

    loaded = _store_and_load(raw_engine, events_table, datetime(2026, 10, 19, 7, 30, tzinfo=five_hours_behind))

    assert loaded == datetime(2026, 10, 19, 12, 30, tzinfo=timezone.utc)
    assert loaded.tzinfo == timezone.utc


def test_utc_datetime_rejects_naive_datetimes(raw_engine, events_table):
    with pytest.raises(StatementError, match="timezone-aware"):
        with raw_engine.begin() as connection:
            connection.execute(insert(events_table).values(id=1, at=datetime(2026, 10, 19, 12, 30)))


def test_utc_datetime_allows_null(raw_engine, events_table):
    assert _store_and_load(raw_engine, events_table, None) is None
