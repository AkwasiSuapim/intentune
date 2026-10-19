"""SQLite-backed listener repository and unit of work, against a migrated database."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.domain.listener import ListenerProfile, new_default_listener_profile
from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.migrations import upgrade_database
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork

_NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def _profile_count(engine):
    with engine.connect() as connection:
        return connection.exec_driver_sql("SELECT COUNT(*) FROM listener_profiles").scalar()


def _non_default_profile():
    return ListenerProfile(listener_profile_id=str(uuid.uuid4()), is_default=False, created_at=_NOW)


# --- Repository ------------------------------------------------------------


def test_added_profile_can_be_read_back_by_id(unit_of_work):
    profile = new_default_listener_profile(now=_NOW)
    with unit_of_work:
        unit_of_work.listener_profiles.add(profile)
        unit_of_work.commit()

    with unit_of_work:
        loaded = unit_of_work.listener_profiles.get(profile.listener_profile_id)

    assert loaded == profile
    assert loaded.created_at.tzinfo == timezone.utc


def test_get_returns_none_for_an_unknown_id(unit_of_work):
    with unit_of_work:
        assert unit_of_work.listener_profiles.get(str(uuid.uuid4())) is None


def test_get_default_returns_none_before_the_listener_exists(unit_of_work):
    with unit_of_work:
        assert unit_of_work.listener_profiles.get_default() is None


def test_get_default_ignores_non_default_profiles(unit_of_work):
    default = new_default_listener_profile(now=_NOW)
    with unit_of_work:
        unit_of_work.listener_profiles.add(_non_default_profile())
        unit_of_work.listener_profiles.add(default)
        unit_of_work.listener_profiles.add(_non_default_profile())
        unit_of_work.commit()

    with unit_of_work:
        assert unit_of_work.listener_profiles.get_default() == default


def test_committing_a_second_default_profile_fails_and_keeps_the_first(engine, unit_of_work):
    first = new_default_listener_profile(now=_NOW)
    with unit_of_work:
        unit_of_work.listener_profiles.add(first)
        unit_of_work.commit()

    with pytest.raises(IntegrityError):
        with unit_of_work:
            unit_of_work.listener_profiles.add(new_default_listener_profile(now=_NOW))
            unit_of_work.commit()

    assert _profile_count(engine) == 1
    with unit_of_work:
        assert unit_of_work.listener_profiles.get_default() == first


# --- Unit of work ----------------------------------------------------------


def test_leaving_without_commit_discards_changes(engine, unit_of_work):
    with unit_of_work:
        unit_of_work.listener_profiles.add(new_default_listener_profile(now=_NOW))

    assert _profile_count(engine) == 0


def test_an_exception_rolls_back_and_propagates(engine, unit_of_work):
    with pytest.raises(RuntimeError, match="boom"):
        with unit_of_work:
            unit_of_work.listener_profiles.add(new_default_listener_profile(now=_NOW))
            raise RuntimeError("boom")

    assert _profile_count(engine) == 0


def test_explicit_rollback_discards_staged_changes(engine, unit_of_work):
    with unit_of_work:
        unit_of_work.listener_profiles.add(new_default_listener_profile(now=_NOW))
        unit_of_work.rollback()
        unit_of_work.commit()

    assert _profile_count(engine) == 0


def test_staged_changes_are_visible_inside_the_same_unit_of_work(unit_of_work):
    profile = new_default_listener_profile(now=_NOW)
    with unit_of_work:
        unit_of_work.listener_profiles.add(profile)

        assert unit_of_work.listener_profiles.get_default() == profile


def test_uncommitted_changes_are_invisible_to_another_unit_of_work(session_factory):
    writer = SqlAlchemyUnitOfWork(session_factory)
    reader = SqlAlchemyUnitOfWork(session_factory)

    with writer:
        writer.listener_profiles.add(new_default_listener_profile(now=_NOW))
        writer.listener_profiles.get_default()  # flushes the insert inside the writer's transaction

        with reader:
            assert reader.listener_profiles.get_default() is None


def test_a_unit_of_work_can_be_reused_for_consecutive_transactions(engine, unit_of_work):
    with unit_of_work:
        unit_of_work.listener_profiles.add(_non_default_profile())
        unit_of_work.commit()
    with unit_of_work:
        unit_of_work.listener_profiles.add(_non_default_profile())
        unit_of_work.commit()

    assert _profile_count(engine) == 2


def test_unit_of_work_is_not_re_entrant(unit_of_work):
    with unit_of_work:
        with pytest.raises(RuntimeError, match="not re-entrant"):
            unit_of_work.__enter__()


@pytest.mark.parametrize(
    "use",
    [lambda uow: uow.listener_profiles, lambda uow: uow.commit(), lambda uow: uow.rollback()],
    ids=["repository", "commit", "rollback"],
)
def test_unit_of_work_refuses_use_outside_a_with_block(unit_of_work, use):
    with pytest.raises(RuntimeError, match="not active"):
        use(unit_of_work)

    with unit_of_work:
        pass

    with pytest.raises(RuntimeError, match="not active"):
        use(unit_of_work)


# --- Default local listener, end to end ------------------------------------


def test_ensure_default_listener_creates_one_generated_profile(engine, unit_of_work):
    profile = ensure_default_listener(unit_of_work, now=_NOW)

    assert uuid.UUID(profile.listener_profile_id).version == 4
    assert profile.is_default is True
    assert profile.created_at == _NOW
    assert _profile_count(engine) == 1


def test_ensure_default_listener_is_idempotent(engine, unit_of_work):
    first = ensure_default_listener(unit_of_work, now=_NOW)
    second = ensure_default_listener(unit_of_work)

    assert second == first
    assert _profile_count(engine) == 1


def test_default_listener_survives_a_restart(migrated_database_url):
    engine = create_database_engine(migrated_database_url)
    try:
        created = ensure_default_listener(SqlAlchemyUnitOfWork(create_session_factory(engine)), now=_NOW)
    finally:
        engine.dispose()

    restarted_engine = create_database_engine(migrated_database_url)
    try:
        after_restart = ensure_default_listener(SqlAlchemyUnitOfWork(create_session_factory(restarted_engine)))
        assert after_restart == created
        assert _profile_count(restarted_engine) == 1
    finally:
        restarted_engine.dispose()


def test_separate_databases_generate_different_listeners(tmp_path):
    ids = []
    for name in ("first.db", "second.db"):
        url = f"sqlite:///{(tmp_path / name).as_posix()}"
        upgrade_database(url)
        engine = create_database_engine(url)
        try:
            ids.append(ensure_default_listener(SqlAlchemyUnitOfWork(create_session_factory(engine))).listener_profile_id)
        finally:
            engine.dispose()

    assert ids[0] != ids[1]
    assert "user1" not in ids
