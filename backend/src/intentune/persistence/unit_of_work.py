"""SQLAlchemy unit of work: the UnitOfWork port (ports/unit_of_work.py) over one ORM session.

Each ``with`` block opens a new session -- one transaction -- and binds fresh
repositories to it. commit() makes the staged changes durable. Leaving the
block always rolls back whatever was not committed and closes the session,
so an exception or an early return never leaves a half-written change.

Keep these transactions short: SQLite allows one writer at a time.
"""

from types import TracebackType
from typing import Optional, Type

from sqlalchemy.orm import Session, sessionmaker

from src.intentune.persistence.repositories import SqlAlchemyListenerProfileRepository


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Optional[Session] = None
        self._listener_profiles: Optional[SqlAlchemyListenerProfileRepository] = None

    @property
    def listener_profiles(self) -> SqlAlchemyListenerProfileRepository:
        if self._listener_profiles is None:
            raise RuntimeError("The unit of work is not active; use it in a 'with' block")
        return self._listener_profiles

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        if self._session is not None:
            raise RuntimeError("The unit of work is already active; it is not re-entrant")
        self._session = self._session_factory()
        self._listener_profiles = SqlAlchemyListenerProfileRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        session = self._session
        self._session = None
        self._listener_profiles = None
        if session is None:
            return
        try:
            session.rollback()
        finally:
            session.close()

    def commit(self) -> None:
        self._active_session().commit()

    def rollback(self) -> None:
        self._active_session().rollback()

    def _active_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("The unit of work is not active; use it in a 'with' block")
        return self._session
