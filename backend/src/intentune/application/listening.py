"""Application use cases: start and steer a listening session with its queue kept current (Prototype 1, phase B8).

The API's session commands, each one use case:

- start(): start a session with this intent, then surface its first queue.
- steer(): apply a steering turn (refine, next, not for me, more like this,
  surprise me, more familiar, try something different), then re-rank the
  queue (spec §21). A NEXT turn while nothing plays starts the first queued
  track: this is how listening begins after a start ("Play").

Each is two steps, as FeedbackService's are (B6): SessionService records the
change in one transaction, then RecommendationService.refresh_queue()
surfaces Policy v1's choice in another. If the refresh fails, the change
stays recorded, and the next command refreshes the queue again.
"""

from typing import Optional, Tuple

from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.session import SessionState, SessionTurn, TurnKind


class ListeningService:
    def __init__(self, sessions: SessionService, recommendations: RecommendationService) -> None:
        self._sessions = sessions
        self._recommendations = recommendations

    def start(self, listener_profile_id: str, context: ListeningContext) -> SessionState:
        """Start a session (the listener's previous one ends) and surface its first queue. Nothing plays yet."""
        started = self._sessions.start_session(listener_profile_id, context)
        return self._recommendations.refresh_queue(started.session.session_id)

    def steer(
        self,
        session_id: str,
        kind: TurnKind,
        context: Optional[ListeningContext] = None,
        occurrence_id: Optional[str] = None,
    ) -> Tuple[SessionTurn, SessionState]:
        """Record a steering turn, then re-rank the queue. Returns the turn and the session after the refresh."""
        turn = self._sessions.apply_turn(session_id, kind, context=context, occurrence_id=occurrence_id)
        return turn, self._recommendations.refresh_queue(session_id)
