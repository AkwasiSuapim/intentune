"""Application use case: refresh a session's upcoming queue with Recommendation Policy v1 (Prototype 1, phases B5, B6).

refresh_queue() reads the session (its context, turns, occurrences, and,
since B6, feedback events) and the library, asks the policy
(domain/policy.py) for the next tracks, and
surfaces them through SessionService.queue_recommendations(), with the
policy version as the algorithm and its exploration pick marked. Whatever was
still queued becomes REPLACED.

Callers refresh after anything meaningful: a session start, a refinement,
a steering turn, or feedback (FeedbackService refreshes after every event,
B6). This re-ranks the remaining candidates immediately (spec §21). Nothing
calls it from a running entry point until B8.

A steering control (Surprise me, Try something different, More familiar) is
acted on by the next refresh_queue() and only that one: surfacing the queue
uses it up. decide() does not, and a refinement made in between supersedes it.

Inputs that do not exist yet stay absent rather than being invented:

- No long-term profile is stored until B10, so long-term fit is unavailable
  and its weight is renormalized away.
- Library tracks carry genre and mood labels only when their tags declare
  them, and no energy, danceability, valence, acousticness, or tempo (B3
  measures signal levels only). Features a track lacks are left out of its
  score, never filled in.
"""

import random
from datetime import datetime, timezone
from typing import Callable, Optional

from src.intentune.application.sessions import SessionService
from src.intentune.domain.policy import POLICY_V1, PolicyDecision, RecommendationPolicy, candidate_from_track, decide, signals_from_session
from src.intentune.domain.session import InvalidSessionTransition, SessionNotFound, SessionState
from src.intentune.ports.unit_of_work import UnitOfWork


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecommendationService:
    def __init__(
        self,
        unit_of_work: UnitOfWork,
        policy: RecommendationPolicy = POLICY_V1,
        rng: Optional[random.Random] = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._uow = unit_of_work
        self._policy = policy
        self._rng = rng if rng is not None else random.Random()
        self._sessions = SessionService(unit_of_work, clock=clock)
        self.last_decision: Optional[PolicyDecision] = None  # the decision of the latest refresh_queue()

    @property
    def policy(self) -> RecommendationPolicy:
        return self._policy

    def refresh_queue(self, session_id: str) -> SessionState:
        """Replace the session's upcoming queue with Policy v1's current choice. This draws from the generator."""
        decision = self._decide(session_id)
        state = self._sessions.queue_recommendations(
            session_id,
            decision.recommendations(),
            self._policy.version,
            exploration_track_ids=decision.exploration_track_ids,
        )
        self.last_decision = decision
        return state

    def decide(self, session_id: str) -> PolicyDecision:
        """A read-only preview: what refresh_queue() would choose now, changing nothing.

        It writes nothing, does not use up a pending control, and leaves the
        generator where it was: the same decision runs on the service's generator,
        whose state is then restored. So a preview never changes what the next
        refresh chooses, and it shows exactly that choice.
        """
        state = self._rng.getstate()
        try:
            return self._decide(session_id)
        finally:
            self._rng.setstate(state)

    def _decide(self, session_id: str) -> PolicyDecision:
        with self._uow:
            session = self._uow.listening_sessions.get(session_id)
            if session is None:
                raise SessionNotFound(session_id)
            if not session.is_active:
                raise InvalidSessionTransition("The session has ended. Start a new session to keep listening.")
            tracks = {track.track_id: track for track in self._uow.tracks.list_all()}
            turns = self._uow.session_turns.list_for_session(session_id)
            occurrences = self._uow.recommendation_occurrences.list_for_session(session_id)
            events = self._uow.feedback_events.list_for_session(session_id)

        signals = signals_from_session(session, turns, occurrences, tracks, self._policy, feedback_events=events)
        candidates = [candidate_from_track(track) for track in tracks.values()]
        return decide(candidates, signals, self._policy, self._rng)
