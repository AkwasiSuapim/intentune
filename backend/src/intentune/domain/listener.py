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

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.intentune.domain.validation import new_uuid, require_canonical_uuid, require_utc_datetime


@dataclass(frozen=True)
class ListenerProfile:
    """The identity of one listener on this device."""

    listener_profile_id: str
    is_default: bool
    created_at: datetime

    def __post_init__(self) -> None:
        require_canonical_uuid(self.listener_profile_id, "listener_profile_id")
        if not isinstance(self.is_default, bool):
            raise ValueError("is_default must be a bool")
        # frozen=True forbids normal assignment; this is the documented way to
        # normalize a field during __post_init__.
        object.__setattr__(self, "created_at", require_utc_datetime(self.created_at, "created_at"))


def new_default_listener_profile(now: Optional[datetime] = None) -> ListenerProfile:
    """Generate the default local listener: a fresh random UUID, created now (UTC)."""
    created_at = now if now is not None else datetime.now(timezone.utc)
    return ListenerProfile(
        listener_profile_id=new_uuid(),
        is_default=True,
        created_at=created_at,
    )
