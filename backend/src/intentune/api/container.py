"""The composition root (B8): the one place that picks the adapters and wires the services.

The adapters and the database engine are built once. Services are built
fresh for each request, each request with its own unit of work, because a unit
of work is neither re-entrant nor thread-safe and FastAPI runs synchronous
routes on a thread pool. The analysis worker and the library scans get their
own units of work the same way.

start() and stop() are the backend's startup and shutdown:

    start: migrate the database -> make sure the local listener exists ->
           end sessions a previous run left active (D35) -> start the analysis
           worker (D28) -> start the incremental startup scan (D25, D26)
    stop:  stop the worker after its current job -> wait for a running scan
           -> close the database connections
"""

import logging
import random
from typing import Callable, Optional

from src.intentune.adapters.local_folders import LocalSourceFolders
from src.intentune.adapters.managed_media import LocalManagedMedia
from src.intentune.adapters.deterministic_intent import DeterministicIntentInterpreter
from src.intentune.adapters.mutagen_audio import MutagenAudioInspector
from src.intentune.adapters.signal_levels import SignalLevelAnalyzer
from src.intentune.api.settings import ApiSettings
from src.intentune.application.analysis import AnalysisService
from src.intentune.application.analysis_worker import AnalysisWorker
from src.intentune.application.capability import IntentCapability
from src.intentune.application.feedback import FeedbackService
from src.intentune.application.library import LibraryService
from src.intentune.application.library_scans import LibraryScanCoordinator
from src.intentune.application.listening import ListeningService
from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.application.messages import MessageService
from src.intentune.application.playlists import PlaylistService
from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.migrations import upgrade_database
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork

logger = logging.getLogger("intentune.api")

_SHUTDOWN_WAIT_SECONDS = 30.0


class Container:
    def __init__(self, settings: ApiSettings, rng_factory: Callable[[], random.Random] = random.Random) -> None:
        self.settings = settings
        self._rng_factory = rng_factory
        self._engine = create_database_engine(settings.database_url)
        self._session_factory = create_session_factory(self._engine)
        self._media = LocalManagedMedia(settings.media_root)
        self._folders = LocalSourceFolders(excluded_directories=[self._media.root])
        self._inspector = MutagenAudioInspector()
        self._analyzer = SignalLevelAnalyzer()
        self._interpreter = DeterministicIntentInterpreter()
        self.worker = AnalysisWorker(self.analysis(), idle_seconds=settings.analysis_idle_seconds)
        self.scans = LibraryScanCoordinator(self.library, on_scanned=self.worker.wake)
        self._listener_profile_id: Optional[str] = None

    # --- Startup and shutdown ---------------------------------------------------------

    def start(self) -> None:
        upgrade_database(self.settings.database_url)
        self._listener_profile_id = ensure_default_listener(self._unit_of_work()).listener_profile_id
        ended = self.sessions().end_sessions_from_previous_run()
        if ended:
            logger.info("Ended %d session(s) left active by a previous run", ended)
        if self.settings.start_worker:
            self.worker.start()
        if self.settings.startup_scan:
            self.scans.start_background_rescan()

    def stop(self) -> None:
        if not self.worker.stop(timeout=_SHUTDOWN_WAIT_SECONDS):
            logger.warning("The analysis worker did not stop in time; its job is recovered at the next start")
        if not self.scans.wait(timeout=_SHUTDOWN_WAIT_SECONDS):
            logger.warning("A library scan was still running at shutdown; the next scan picks up where it stopped")
        self._engine.dispose()

    @property
    def listener_profile_id(self) -> str:
        """The local listener (D01). Known once start() has run."""
        if self._listener_profile_id is None:
            raise RuntimeError("The backend has not started.")
        return self._listener_profile_id

    # --- Services, fresh for each caller ----------------------------------------------

    def library(self) -> LibraryService:
        return LibraryService(self._unit_of_work(), self._folders, self._inspector, self._media)

    def analysis(self) -> AnalysisService:
        return AnalysisService(self._unit_of_work(), self._analyzer, self._media)

    def sessions(self) -> SessionService:
        return SessionService(self._unit_of_work())

    def listening(self) -> ListeningService:
        unit_of_work = self._unit_of_work()
        return ListeningService(SessionService(unit_of_work), self._recommendations(unit_of_work), IntentCapability(unit_of_work))

    def capability(self) -> IntentCapability:
        return IntentCapability(self._unit_of_work())

    def messages(self) -> MessageService:
        unit_of_work = self._unit_of_work()
        recommendations = self._recommendations(unit_of_work)
        sessions = SessionService(unit_of_work)
        capability = IntentCapability(unit_of_work)
        return MessageService(
            self._interpreter,
            sessions,
            ListeningService(sessions, recommendations, capability),
            FeedbackService(unit_of_work, recommendations),
            capability,
        )

    def feedback(self) -> FeedbackService:
        unit_of_work = self._unit_of_work()
        return FeedbackService(unit_of_work, self._recommendations(unit_of_work))

    def playlists(self) -> PlaylistService:
        unit_of_work = self._unit_of_work()
        return PlaylistService(unit_of_work, FeedbackService(unit_of_work, self._recommendations(unit_of_work)))

    def _recommendations(self, unit_of_work: SqlAlchemyUnitOfWork) -> RecommendationService:
        return RecommendationService(unit_of_work, rng=self._rng_factory())

    def _unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory)
