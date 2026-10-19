"""ListenerProfileRepository port: storage for the local listener identity.

Describes what the application needs from listener-profile storage without
naming SQLAlchemy, SQLite, or any table. The SQLite implementation lives in
src/intentune/persistence/repositories.py; tests can use an in-memory fake.

A repository only stages changes. Making them durable is the job of the
unit of work that owns it (see ports/unit_of_work.py).
"""

from typing import Optional, Protocol

from src.intentune.domain.listener import ListenerProfile


class ListenerProfileRepository(Protocol):
    """Reads and stages ListenerProfile changes inside one unit of work."""

    def get(self, listener_profile_id: str) -> Optional[ListenerProfile]:
        """Return the profile with this id, or None if there is none."""
        ...

    def get_default(self) -> Optional[ListenerProfile]:
        """Return the default local listener, or None if it has not been created yet."""
        ...

    def add(self, profile: ListenerProfile) -> None:
        """Stage a new profile. It becomes durable when the unit of work commits."""
        ...
