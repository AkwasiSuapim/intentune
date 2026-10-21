"""Application use case: refresh a session's upcoming queue with Recommendation Policy v1 (Prototype 1, phase B5).

refresh_queue() reads the session (its context, turns, and occurrences) and
the library, asks the policy (domain/policy.py) for the next tracks, and
surfaces them through SessionService.queue_recommendations(), with the
policy version as the algorithm and its exploration pick marked. Whatever was
still queued becomes REPLACED.

Callers refresh after anything meaningful: a session start, a refinement,
a steering turn, or (from B6) feedback. This re-ranks the remaining
candidates immediately (spec §21). Nothing calls it from a running entry
point until B8.

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
        self.last_decision: Optional[PolicyDecision] = None

    def refresh_queue(self, session_id: str) -> SessionState:
        """Replace the session's upcoming queue with Policy v1's current choice."""
        decision = self.decide(session_id)
        return self._sessions.queue_recommendations(
            session_id,
            decision.recommendations(),
            self._policy.version,
            exploration_track_ids=decision.exploration_track_ids,
        )

    def decide(self, session_id: str) -> PolicyDecision:
        """What Policy v1 would queue now, without changing the session (for refresh and for explanations)."""
        with self._uow:
            session = self._uow.listening_sessions.get(session_id)
            if session is None:
                raise SessionNotFound(session_id)
            if not session.is_active:
                raise InvalidSessionTransition("The session has ended. Start a new session to keep listening.")
            tracks = {track.track_id: track for track in self._uow.tracks.list_all()}
            turns = self._uow.session_turns.list_for_session(session_id)
            occurrences = self._uow.recommendation_occurrences.list_for_session(session_id)

        signals = signals_from_session(session, turns, occurrences, tracks, self._policy)
        candidates = [candidate_from_track(track) for track in tracks.values()]
        decision = decide(candidates, signals, self._policy, self._rng)
        self.last_decision = decision
        return decision
