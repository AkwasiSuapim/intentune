"""SQLAlchemy repositories: implement the storage ports over ORM records.

A repository works inside a Session it is given and never commits; the unit
of work that created it owns the transaction (see unit_of_work.py). It
accepts and returns domain models only, so ORM records stay inside the
persistence package.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.intentune.domain.listener import ListenerProfile
from src.intentune.persistence.models import ListenerProfileRecord


def _listener_profile_from_record(record: ListenerProfileRecord) -> ListenerProfile:
    return ListenerProfile(
        listener_profile_id=record.id,
        is_default=record.is_default,
        created_at=record.created_at,
    )


class SqlAlchemyListenerProfileRepository:
    """ListenerProfileRepository port implementation (see ports/listener_profiles.py)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, listener_profile_id: str) -> Optional[ListenerProfile]:
        record = self._session.get(ListenerProfileRecord, listener_profile_id)
        return _listener_profile_from_record(record) if record is not None else None

    def get_default(self) -> Optional[ListenerProfile]:
        statement = select(ListenerProfileRecord).where(ListenerProfileRecord.is_default.is_(True))
        record = self._session.scalars(statement).one_or_none()
        return _listener_profile_from_record(record) if record is not None else None

    def add(self, profile: ListenerProfile) -> None:
        self._session.add(
            ListenerProfileRecord(
                id=profile.listener_profile_id,
                is_default=profile.is_default,
                created_at=profile.created_at,
            )
        )
