"""Pure application tests for ensure_default_listener(), using an in-memory fake unit of work."""

from datetime import datetime, timezone

from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.domain.listener import ListenerProfile

_NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


class _FakeListenerProfileRepository:
    def __init__(self, profiles):
        self.profiles = list(profiles)
        self.added = []

    def get(self, listener_profile_id):
        return next((p for p in self.profiles if p.listener_profile_id == listener_profile_id), None)

    def get_default(self):
        return next((p for p in self.profiles if p.is_default), None)

    def add(self, profile):
        self.added.append(profile)


class _FakeUnitOfWork:
    def __init__(self, profiles=()):
        self.listener_profiles = _FakeListenerProfileRepository(profiles)
        self.commits = 0
        self.entered = 0
        self.exited = 0

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exited += 1

    def commit(self):
        self.listener_profiles.profiles.extend(self.listener_profiles.added)
        self.listener_profiles.added.clear()
        self.commits += 1

    def rollback(self):
        self.listener_profiles.added.clear()


def test_creates_and_commits_the_default_listener_on_first_run():
    unit_of_work = _FakeUnitOfWork()

    profile = ensure_default_listener(unit_of_work, now=_NOW)

    assert profile.is_default is True
    assert profile.created_at == _NOW
    assert unit_of_work.listener_profiles.profiles == [profile]
    assert unit_of_work.commits == 1


def test_returns_the_existing_default_listener_without_writing():
    existing = ListenerProfile(
        listener_profile_id="3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e",
        is_default=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    unit_of_work = _FakeUnitOfWork([existing])

    profile = ensure_default_listener(unit_of_work, now=_NOW)

    assert profile == existing
    assert unit_of_work.commits == 0
    assert unit_of_work.listener_profiles.added == []


def test_ignores_non_default_profiles_when_looking_for_the_default():
    other = ListenerProfile(
        listener_profile_id="9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
        is_default=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    unit_of_work = _FakeUnitOfWork([other])

    profile = ensure_default_listener(unit_of_work, now=_NOW)

    assert profile != other
    assert profile.is_default is True
    assert unit_of_work.commits == 1


def test_runs_inside_exactly_one_unit_of_work_block():
    unit_of_work = _FakeUnitOfWork()

    ensure_default_listener(unit_of_work, now=_NOW)

    assert unit_of_work.entered == 1
    assert unit_of_work.exited == 1
