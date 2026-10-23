"""UnitOfWork port: one atomic transaction spanning the repositories a use case needs.

An application use case opens a unit of work with ``with``, reads and stages
changes through its repositories, and calls commit() when the whole change is
complete. Leaving the block without commit() -- by returning early or by an
exception -- discards every staged change. Nothing is written by accident.

Each ``with`` block is a fresh transaction. A unit of work is not re-entrant.

Prototype 1 phases add repositories here as they create them: listener
profiles in B1; library sources, source files, and tracks in B2; analysis
jobs and track features in B3; sessions in B4; playlists in B7; long-term
profiles and their adjustments in B10.

A unit of work is not thread-safe. Each thread (for example the background
analysis worker) uses its own instance.
"""

from types import TracebackType
from typing import Optional, Protocol, Type

from src.intentune.ports.adaptation import LongTermProfileRepository
from src.intentune.ports.analysis import AnalysisJobRepository, TrackFeatureRepository
from src.intentune.ports.library import LibrarySourceRepository, SourceFileRepository, TrackRepository
from src.intentune.ports.listener_profiles import ListenerProfileRepository
from src.intentune.ports.playlists import PlaylistRepository
from src.intentune.ports.sessions import (
    FeedbackEventRepository,
    ListeningSessionRepository,
    RecommendationOccurrenceRepository,
    SessionTurnRepository,
)


class UnitOfWork(Protocol):
    """A transaction boundary that exposes the repositories bound to it."""

    @property
    def listener_profiles(self) -> ListenerProfileRepository:
        """The listener-profile repository for the active transaction."""
        ...

    @property
    def library_sources(self) -> LibrarySourceRepository:
        ...

    @property
    def source_files(self) -> SourceFileRepository:
        ...

    @property
    def tracks(self) -> TrackRepository:
        ...

    @property
    def analysis_jobs(self) -> AnalysisJobRepository:
        ...

    @property
    def track_features(self) -> TrackFeatureRepository:
        ...

    @property
    def listening_sessions(self) -> ListeningSessionRepository:
        ...

    @property
    def session_turns(self) -> SessionTurnRepository:
        ...

    @property
    def recommendation_occurrences(self) -> RecommendationOccurrenceRepository:
        ...

    @property
    def feedback_events(self) -> FeedbackEventRepository:
        ...

    @property
    def playlists(self) -> PlaylistRepository:
        ...

    @property
    def long_term_profiles(self) -> LongTermProfileRepository:
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
