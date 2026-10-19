"""Shared fixtures for persistence tests.

Every database here is a fresh SQLite file under pytest's tmp_path. No test
opens backend/data/intentune.db or depends on the DATABASE_URL variable.
"""

import pytest

from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.migrations import upgrade_database
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def database_url(tmp_path):
    """A URL for a database file that does not exist yet."""
    return f"sqlite:///{(tmp_path / 'intentune-test.db').as_posix()}"


@pytest.fixture
def migrated_database_url(database_url):
    """A database upgraded to the latest migration."""
    upgrade_database(database_url)
    return database_url


@pytest.fixture
def engine(migrated_database_url):
    engine = create_database_engine(migrated_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    return create_session_factory(engine)


@pytest.fixture
def unit_of_work(session_factory):
    return SqlAlchemyUnitOfWork(session_factory)
