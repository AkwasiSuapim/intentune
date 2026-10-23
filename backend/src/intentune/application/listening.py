"""Application use cases: start and steer a listening session with its queue kept current (Prototype 1, phases B8, B9).

The API's session commands, each one use case:

- start(): start a session with this intent, then surface its first queue.
- steer(): apply a steering turn (refine, not for me, more like this,
  surprise me, more familiar, try something different), then re-rank the
  queue (spec §21).
- next() (B9): the listener moves on. While nothing plays, it starts the first
  queued track: this is how listening begins after a start ("Play"). Ending a
  track early, the player may report how far it got. That is recorded as the
  SKIP fact about the track that ended, so the clicked Next and the typed
  "next" record the same evidence through this one use case.

Each is two steps, as FeedbackService's are (B6): SessionService records the
change, then RecommendationService.refresh_queue() surfaces Policy v1's
choice. If the refresh fails, the change stays recorded, and the next command
refreshes the queue again.

A Not for me turn, and the SKIP a Next records, can change a track's
long-term evidence, so the long-term profile is brought in line
(LongTermAdaptationService, B10) after they are recorded and before the one
refresh. A More like this turn steers the session only and is not long-term
evidence.

Before a start or a REFINE records anything, IntentCapability checks it
against the library as it is now (B9). With no playable tracks, nothing can be
recommended: LibraryNotReady. An intent that sets a dimension the library has
no usable data for raises IntentUnavailable. Either way nothing is started,
recorded, or surfaced. Typed refinements arrive here too, so both kinds of
input meet the same rule.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from src.intentune.application.adaptation import LongTermAdaptationService
from src.intentune.application.capability import IntentCapability
from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.session import FeedbackEventType, SessionState, SessionTurn, TurnKind


@dataclass(frozen=True)
class PlaybackFacts:
    """How far the player got through a track, as it measured: the facts a SKIP records (spec §22)."""

    played_seconds: float
    duration_seconds: float


class ListeningService:
    def __init__(
        self,
        sessions: SessionService,
        recommendations: RecommendationService,
        capability: IntentCapability,
        adaptation: LongTermAdaptationService,
    ) -> None:
        self._sessions = sessions
        self._recommendations = recommendations
        self._capability = capability
        self._adaptation = adaptation

    def start(self, listener_profile_id: str, context: ListeningContext) -> SessionState:
        """Start a session (the listener's previous one ends) and surface its first queue. Nothing plays yet.

        Refused, before anything changes, if the library is not ready or the intent asks for what it cannot act on.
        """
        self._capability.require(ListeningContext(), context)
        started = self._sessions.start_session(listener_profile_id, context)
        return self._recommendations.refresh_queue(started.session.session_id)

    def steer(
        self,
        session_id: str,
        kind: TurnKind,
        context: Optional[ListeningContext] = None,
        occurrence_id: Optional[str] = None,
    ) -> Tuple[SessionTurn, SessionState]:
        """Record a steering turn, then re-rank the queue. Returns the turn and the session after the refresh.

        A REFINE is refused, before anything changes, if the library is not ready or the new intent asks for what it
        cannot act on.
        """
        if kind is TurnKind.REFINE and context is not None:
            self._capability.require(self._sessions.get_session(session_id).session.current_context, context)
        turn = self._sessions.apply_turn(session_id, kind, context=context, occurrence_id=occurrence_id)
        if turn.kind is TurnKind.NOT_FOR_ME:  # More like this steers the session only: no long-term evidence
            self._adaptation.adapt_after(session_id)
        return turn, self._recommendations.refresh_queue(session_id)

    def next(
        self,
        session_id: str,
        occurrence_id: Optional[str] = None,
        playback: Optional[PlaybackFacts] = None,
    ) -> Tuple[SessionTurn, SessionState]:
        """Move on: the NEXT turn, the SKIP fact about the track it ended (when the player reported one), then re-rank.

        occurrence_id, when given, must be the playing occurrence. The SKIP is
        recorded after the turn, as a report about an occurrence that has just
        finished, so it moves nothing a second time (B6).
        """
        turn = self._sessions.apply_turn(session_id, TurnKind.NEXT, occurrence_id=occurrence_id)
        if playback is not None and turn.occurrence_id is not None:
            self._sessions.record_feedback(
                session_id, turn.occurrence_id, FeedbackEventType.SKIP, playback.played_seconds, playback.duration_seconds
            )
            self._adaptation.adapt_after(session_id)
        return turn, self._recommendations.refresh_queue(session_id)
