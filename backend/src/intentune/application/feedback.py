"""Application use cases: record a listener's feedback and adapt the session to it (Prototype 1, phase B6).

Execution guide §9: persist the raw event -> interpret -> update session
evidence -> re-rank the queue.

- react(): an explicit action about an occurrence: LIKE, SAVE, REPLAY, or NOT_FOR_ME,
  or UNLIKE (B9), which takes a Like back.
- report_playback(): how a track's playback ended: SKIP or COMPLETE, with the
  seconds played and the track's duration as the player reported them.
- record_playlist_add() (B7): PLAYLIST_ADD, called by PlaylistService when the
  listener adds a recommendation to a playlist.

Each call has three steps:
1. SessionService.record_feedback() stores the raw fact and moves playback on,
   if the event ends or replays a track (one transaction).
2. LongTermAdaptationService.adapt_after() (B10) brings the long-term profile in
   line with the history, recording any bounded adjustment. It refreshes
   nothing.
3. RecommendationService.refresh_queue() re-ranks and refills the queue, once,
   so the next tracks reflect the feedback at once (D05, D16).

Session evidence is not stored. Policy v1 reads every raw event through
Feedback Policy v1 at each refresh (domain/policy.py, interpret_feedback()),
per track in the session, so the thresholds can change later without losing
evidence. The long-term profile changes only through step 2, by Long-Term
Adaptation Policy v1's gate (D06); Not for me still excludes a track for this
session only (D18).

Only discrete events are accepted; there are no progress ticks (spec §22). The
frontend owns playback position and reports how a track ended.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from src.intentune.application.adaptation import LongTermAdaptationService
from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.policy import Interpretation, event_weight, interpret_feedback
from src.intentune.domain.session import FeedbackEvent, FeedbackEventType, SessionState
from src.intentune.ports.unit_of_work import UnitOfWork

REACTIONS = frozenset(
    {FeedbackEventType.LIKE, FeedbackEventType.UNLIKE, FeedbackEventType.SAVE, FeedbackEventType.REPLAY, FeedbackEventType.NOT_FOR_ME}
)
PLAYBACK_ENDINGS = frozenset({FeedbackEventType.SKIP, FeedbackEventType.COMPLETE})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FeedbackOutcome:
    """What one piece of feedback did.

    event_weight is what the event means on its own under Feedback Policy v1.
    interpretation is what everything about its track in this session now
    means, explicit actions taking precedence over passive playback. state is
    the session after the queue was re-ranked.
    """

    event: FeedbackEvent
    event_weight: float
    interpretation: Interpretation
    state: SessionState


class FeedbackService:
    def __init__(
        self,
        unit_of_work: UnitOfWork,
        recommendations: RecommendationService,
        adaptation: LongTermAdaptationService,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._sessions = SessionService(unit_of_work, clock=clock)
        self._recommendations = recommendations
        self._adaptation = adaptation

    def react(self, session_id: str, occurrence_id: str, reaction: FeedbackEventType) -> FeedbackOutcome:
        """Record Like, Unlike, Save, Replay, or Not for me about an occurrence, then re-rank."""
        reaction = FeedbackEventType(reaction)
        if reaction is FeedbackEventType.PLAYLIST_ADD:
            raise ValueError("A playlist add is recorded by PlaylistService.add_track(), with the playlist item it stands for.")
        if reaction not in REACTIONS:
            raise ValueError(f"{reaction.value} is not a reaction; report playback endings with report_playback().")
        return self._record(session_id, occurrence_id, reaction, None, None)

    def record_playlist_add(self, session_id: str, occurrence_id: str) -> FeedbackOutcome:
        """Record that a recommendation was added to a playlist (+1.00, B7), then re-rank.

        Called by PlaylistService.add_track() once the playlist item is stored, never on its own:
        a playlist add is feedback because the listener saved the track, not the other way round.
        """
        return self._record(session_id, occurrence_id, FeedbackEventType.PLAYLIST_ADD, None, None)

    def report_playback(
        self,
        session_id: str,
        occurrence_id: str,
        ending: FeedbackEventType,
        played_seconds: float,
        duration_seconds: float,
    ) -> FeedbackOutcome:
        """Record that an occurrence's playback was skipped or completed, and how much was played, then re-rank."""
        ending = FeedbackEventType(ending)
        if ending not in PLAYBACK_ENDINGS:
            raise ValueError(f"{ending.value} is not a playback ending; record reactions with react().")
        return self._record(session_id, occurrence_id, ending, played_seconds, duration_seconds)

    def _record(
        self,
        session_id: str,
        occurrence_id: str,
        event_type: FeedbackEventType,
        played_seconds: Optional[float],
        duration_seconds: Optional[float],
    ) -> FeedbackOutcome:
        event, _ = self._sessions.record_feedback(session_id, occurrence_id, event_type, played_seconds, duration_seconds)
        self._adaptation.adapt_after(session_id)
        state = self._recommendations.refresh_queue(session_id)
        history = self._sessions.history(session_id)
        track_id = next(occurrence.track_id for occurrence in history.occurrences if occurrence.occurrence_id == occurrence_id)
        same_track = {occurrence.occurrence_id for occurrence in history.occurrences if occurrence.track_id == track_id}
        policy = self._recommendations.policy
        interpretation = interpret_feedback(
            [turn for turn in history.turns if turn.occurrence_id in same_track],
            [recorded for recorded in history.feedback_events if recorded.occurrence_id in same_track],
            policy,
        )
        return FeedbackOutcome(event=event, event_weight=event_weight(event, policy), interpretation=interpretation, state=state)
