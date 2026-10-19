"""UnitOfWork port: one atomic transaction spanning the repositories a use case needs.

An application use case opens a unit of work with ``with``, reads and stages
changes through its repositories, and calls commit() when the whole change is
complete. Leaving the block without commit() -- by returning early or by an
exception -- discards every staged change. Nothing is written by accident.

Each ``with`` block is a fresh transaction. A unit of work is not re-entrant.

Prototype 1 phases add repositories here as they create them (tracks and
sources in B2, sessions in B4, and so on). B1 has only listener profiles.
"""

from types import TracebackType
from typing import Optional, Protocol, Type

from src.intentune.ports.listener_profiles import ListenerProfileRepository


class UnitOfWork(Protocol):
    """A transaction boundary that exposes the repositories bound to it."""

    @property
    def listener_profiles(self) -> ListenerProfileRepository:
        """The listener-profile repository for the active transaction."""
        ...

    def __enter__(self) -> "UnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        ...

    def commit(self) -> None:
        """Make every change staged in this transaction durable."""
        ...

    def rollback(self) -> None:
        """Discard every change staged in this transaction."""
        ...
