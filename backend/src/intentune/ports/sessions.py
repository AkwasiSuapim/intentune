"""Session storage ports: sessions, turns, recommendation occurrences, and feedback events.

Implemented over SQLite in src/intentune/persistence/repositories.py. Like
every repository, these stage changes; the unit of work that owns them
commits. They accept and return domain models only.
"""

from typing import List, Optional, Protocol

from src.intentune.domain.session import FeedbackEvent, ListeningSession, OccurrenceStatus, RecommendationOccurrence, SessionTurn


class ListeningSessionRepository(Protocol):
    def get(self, session_id: str) -> Optional[ListeningSession]:
        ...

    def get_active_for_listener(self, listener_profile_id: str) -> Optional[ListeningSession]:
        ...

    def list_for_listener(self, listener_profile_id: str) -> List[ListeningSession]:
        """Every session of the listener, newest first."""
        ...

    def list_active(self) -> List[ListeningSession]:
        ...

    def add(self, session: ListeningSession) -> None:
        ...

    def save(self, session: ListeningSession) -> None:
        ...


class SessionTurnRepository(Protocol):
    def list_for_session(self, session_id: str) -> List[SessionTurn]:
        """The session's turns in sequence order."""
        ...

    def list_for_listener(self, listener_profile_id: str) -> List[SessionTurn]:
        """The turns of all the listener's sessions, each session's in sequence order (B11: one read for a history)."""
        ...

    def add(self, turn: SessionTurn) -> None:
        ...


class RecommendationOccurrenceRepository(Protocol):
    def get(self, occurrence_id: str) -> Optional[RecommendationOccurrence]:
        ...

    def list_for_session(self, session_id: str, status: Optional[OccurrenceStatus] = None) -> List[RecommendationOccurrence]:
        """The session's occurrences in the order they were surfaced; QUEUED ones in queue order."""
        ...

    def list_for_listener(self, listener_profile_id: str) -> List[RecommendationOccurrence]:
        """The occurrences of all the listener's sessions, each session's in the order they were surfaced."""
        ...

    def add(self, occurrence: RecommendationOccurrence) -> None:
        ...

    def save(self, occurrence: RecommendationOccurrence) -> None:
        ...


class FeedbackEventRepository(Protocol):
    def list_for_session(self, session_id: str) -> List[FeedbackEvent]:
        """The session's raw feedback events in the order they occurred."""
        ...

    def list_for_listener(self, listener_profile_id: str) -> List[FeedbackEvent]:
        """The raw feedback events of all the listener's sessions, each session's in the order they occurred."""
        ...

    def add(self, event: FeedbackEvent) -> None:
        ...
