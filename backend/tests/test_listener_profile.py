import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.intentune.domain.listener import ListenerProfile, new_default_listener_profile

_ID = "3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e"
_CREATED_AT = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def test_valid_listener_profile():
    profile = ListenerProfile(listener_profile_id=_ID, is_default=True, created_at=_CREATED_AT)

    assert profile.listener_profile_id == _ID
    assert profile.is_default is True
    assert profile.created_at == _CREATED_AT


@pytest.mark.parametrize("bad_id", ["", "user1", "not-a-uuid", 42, None])
def test_listener_profile_id_must_be_a_uuid(bad_id):
    with pytest.raises(ValueError):
        ListenerProfile(listener_profile_id=bad_id, is_default=True, created_at=_CREATED_AT)


@pytest.mark.parametrize("non_canonical_id", [_ID.upper(), _ID.replace("-", ""), "{" + _ID + "}"])
def test_listener_profile_id_must_be_canonical(non_canonical_id):
    with pytest.raises(ValueError, match="canonical"):
        ListenerProfile(listener_profile_id=non_canonical_id, is_default=True, created_at=_CREATED_AT)


@pytest.mark.parametrize("bad_flag", [1, 0, "true", None])
def test_is_default_must_be_a_bool(bad_flag):
    with pytest.raises(ValueError, match="is_default"):
        ListenerProfile(listener_profile_id=_ID, is_default=bad_flag, created_at=_CREATED_AT)


def test_naive_created_at_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        ListenerProfile(listener_profile_id=_ID, is_default=True, created_at=datetime(2026, 10, 19, 12, 0))


def test_created_at_is_normalized_to_utc():
    two_hours_ahead = timezone(timedelta(hours=2))
    profile = ListenerProfile(
        listener_profile_id=_ID,
        is_default=True,
        created_at=datetime(2026, 10, 19, 14, 0, tzinfo=two_hours_ahead),
    )

    assert profile.created_at == _CREATED_AT
    assert profile.created_at.tzinfo == timezone.utc


def test_listener_profile_is_immutable():
    profile = ListenerProfile(listener_profile_id=_ID, is_default=True, created_at=_CREATED_AT)

    with pytest.raises(AttributeError):
        profile.is_default = False


def test_new_default_listener_profile_is_generated():
    profile = new_default_listener_profile(now=_CREATED_AT)

    assert uuid.UUID(profile.listener_profile_id).version == 4
    assert profile.is_default is True
    assert profile.created_at == _CREATED_AT


def test_new_default_listener_profiles_get_distinct_ids():
    ids = {new_default_listener_profile().listener_profile_id for _ in range(20)}

    assert len(ids) == 20


def test_new_default_listener_profile_defaults_to_current_utc_time():
    before = datetime.now(timezone.utc)
    profile = new_default_listener_profile()
    after = datetime.now(timezone.utc)

    assert before <= profile.created_at <= after
    assert profile.created_at.tzinfo == timezone.utc
