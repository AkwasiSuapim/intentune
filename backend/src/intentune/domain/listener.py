"""The local listener identity for Prototype 1.

Prototype 1 has no accounts or authentication (decision D01). Instead,
Intentune generates one default local listener profile the first time it
runs, and everything the listener owns -- sessions, feedback, playlists --
will hang off that identity rather than a hard-coded id such as "user1".

ListenerProfile is identity only. Long-term taste preferences stay in
UserProfile (see models.py); attaching them to a listener is a later phase.
The profile deliberately holds no name, email, or other personal data.

Like the rest of the domain, this module has no knowledge of SQLAlchemy,
SQLite, or HTTP. Persistence lives in src/intentune/persistence/.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


def _require_canonical_uuid(value: object, field_name: str) -> str:
    """Require a lowercase, hyphenated UUID string, exactly as str(uuid.UUID(...)) renders it."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a UUID") from error
    if str(parsed) != value:
        raise ValueError(f"{field_name} must be a canonical lowercase UUID string")
    return value


def _require_utc_datetime(value: object, field_name: str) -> datetime:
    """Require a timezone-aware datetime and normalize it to UTC. Naive datetimes are ambiguous."""
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ListenerProfile:
    """The identity of one listener on this device."""

    listener_profile_id: str
    is_default: bool
    created_at: datetime

    def __post_init__(self) -> None:
        _require_canonical_uuid(self.listener_profile_id, "listener_profile_id")
        if not isinstance(self.is_default, bool):
            raise ValueError("is_default must be a bool")
        # frozen=True forbids normal assignment; this is the documented way to
        # normalize a field during __post_init__.
        object.__setattr__(self, "created_at", _require_utc_datetime(self.created_at, "created_at"))


def new_default_listener_profile(now: Optional[datetime] = None) -> ListenerProfile:
    """Generate the default local listener: a fresh random UUID, created now (UTC)."""
    created_at = now if now is not None else datetime.now(timezone.utc)
    return ListenerProfile(
        listener_profile_id=str(uuid.uuid4()),
        is_default=True,
        created_at=created_at,
    )
