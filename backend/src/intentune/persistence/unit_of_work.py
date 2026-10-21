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

from src.intentune.persistence.repositories import (
    SqlAlchemyAnalysisJobRepository,
    SqlAlchemyLibrarySourceRepository,
    SqlAlchemyListenerProfileRepository,
    SqlAlchemySourceFileRepository,
    SqlAlchemyFeedbackEventRepository,
    SqlAlchemyListeningSessionRepository,
    SqlAlchemyPlaylistRepository,
    SqlAlchemyRecommendationOccurrenceRepository,
    SqlAlchemySessionTurnRepository,
    SqlAlchemyTrackFeatureRepository,
    SqlAlchemyTrackRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Optional[Session] = None
        self._listener_profiles: Optional[SqlAlchemyListenerProfileRepository] = None
        self._library_sources: Optional[SqlAlchemyLibrarySourceRepository] = None
        self._source_files: Optional[SqlAlchemySourceFileRepository] = None
        self._tracks: Optional[SqlAlchemyTrackRepository] = None
        self._analysis_jobs: Optional[SqlAlchemyAnalysisJobRepository] = None
        self._track_features: Optional[SqlAlchemyTrackFeatureRepository] = None
        self._listening_sessions: Optional[SqlAlchemyListeningSessionRepository] = None
        self._session_turns: Optional[SqlAlchemySessionTurnRepository] = None
        self._recommendation_occurrences: Optional[SqlAlchemyRecommendationOccurrenceRepository] = None
        self._feedback_events: Optional[SqlAlchemyFeedbackEventRepository] = None
        self._playlists: Optional[SqlAlchemyPlaylistRepository] = None

    @property
    def listener_profiles(self) -> SqlAlchemyListenerProfileRepository:
        return self._active(self._listener_profiles)

    @property
    def library_sources(self) -> SqlAlchemyLibrarySourceRepository:
        return self._active(self._library_sources)

    @property
    def source_files(self) -> SqlAlchemySourceFileRepository:
        return self._active(self._source_files)

    @property
    def tracks(self) -> SqlAlchemyTrackRepository:
        return self._active(self._tracks)

    @property
    def analysis_jobs(self) -> SqlAlchemyAnalysisJobRepository:
        return self._active(self._analysis_jobs)

    @property
    def track_features(self) -> SqlAlchemyTrackFeatureRepository:
        return self._active(self._track_features)

    @property
    def listening_sessions(self) -> SqlAlchemyListeningSessionRepository:
        return self._active(self._listening_sessions)

    @property
    def session_turns(self) -> SqlAlchemySessionTurnRepository:
        return self._active(self._session_turns)

    @property
    def recommendation_occurrences(self) -> SqlAlchemyRecommendationOccurrenceRepository:
        return self._active(self._recommendation_occurrences)

    @property
    def feedback_events(self) -> SqlAlchemyFeedbackEventRepository:
        return self._active(self._feedback_events)

    @property
    def playlists(self) -> SqlAlchemyPlaylistRepository:
        return self._active(self._playlists)

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        if self._session is not None:
            raise RuntimeError("The unit of work is already active; it is not re-entrant")
        self._session = self._session_factory()
        self._listener_profiles = SqlAlchemyListenerProfileRepository(self._session)
        self._library_sources = SqlAlchemyLibrarySourceRepository(self._session)
        self._source_files = SqlAlchemySourceFileRepository(self._session)
        self._tracks = SqlAlchemyTrackRepository(self._session)
        self._analysis_jobs = SqlAlchemyAnalysisJobRepository(self._session)
        self._track_features = SqlAlchemyTrackFeatureRepository(self._session)
        self._listening_sessions = SqlAlchemyListeningSessionRepository(self._session)
        self._session_turns = SqlAlchemySessionTurnRepository(self._session)
        self._recommendation_occurrences = SqlAlchemyRecommendationOccurrenceRepository(self._session)
        self._feedback_events = SqlAlchemyFeedbackEventRepository(self._session)
        self._playlists = SqlAlchemyPlaylistRepository(self._session)
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
        self._library_sources = None
        self._source_files = None
        self._tracks = None
        self._analysis_jobs = None
        self._track_features = None
        self._listening_sessions = None
        self._session_turns = None
        self._recommendation_occurrences = None
        self._feedback_events = None
        self._playlists = None
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

    @staticmethod
    def _active(repository):
        if repository is None:
            raise RuntimeError("The unit of work is not active; use it in a 'with' block")
        return repository
