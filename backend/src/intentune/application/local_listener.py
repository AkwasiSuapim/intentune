"""Application use case: make sure the default local listener exists.

Prototype 1 has one generated local listener instead of accounts (D01). The
first run creates it; every later run finds and returns the same profile, so
the listener's id is stable across restarts.

Depends only on the UnitOfWork port. It has no SQLAlchemy, file, or HTTP
code, and can be tested against an in-memory fake.
"""

from datetime import datetime
from typing import Optional

from src.intentune.domain.listener import ListenerProfile, new_default_listener_profile
from src.intentune.ports.unit_of_work import UnitOfWork


def ensure_default_listener(unit_of_work: UnitOfWork, now: Optional[datetime] = None) -> ListenerProfile:
    """Return the default local listener, generating and storing it on first run.

    `now` fixes the creation time for tests; by default the current UTC time
    is used. It has no effect when the listener already exists.
    """
    with unit_of_work:
        existing = unit_of_work.listener_profiles.get_default()
        if existing is not None:
            return existing

        profile = new_default_listener_profile(now=now)
        unit_of_work.listener_profiles.add(profile)
        unit_of_work.commit()
        return profile
