"""Application use cases for listening sessions (Prototype 1, phase B4).

SessionService keeps where a session is now (status, context, what is
playing, what is queued) and records how it got there (turns and
recommendation occurrences). Every command runs in one transaction and works
only on an ACTIVE session.

- start_session(): a fresh ACTIVE session with its INITIAL_INTENT turn. Any
  session the listener still had ACTIVE ends first, so there is at most one.
- apply_turn(): record a steering action. REFINE replaces the context. NEXT
  finishes the current track and starts the next queued one. NOT_FOR_ME and
  MORE_LIKE_THIS name the occurrence they are about (the playing one by
  default). What turns mean for ranking (exclusion, affinity, exploration) is
  Recommendation Policy v1 (B5) and feedback handling (B6). B4 only records them.
- queue_recommendations(): surface algorithm results as the session's new
  upcoming queue. Recommendations still queued from before become REPLACED.
  Producing the recommendations is B5.
- play() / advance(): start a specific queued occurrence, or the next one.
- end_session(): the listener ends the session.
- end_sessions_from_previous_run(): at startup, end every session a previous
  run left ACTIVE. Their queues are discarded, not resumed, and their history
  is kept (D35).

Recording feedback events (FeedbackEvent) and interpreting them is B6. No raw
conversational text is accepted or stored (D33).

Within a session, every change gets a strictly later time than the one before
(B5), even when the clock has not moved. So turns and surfaced queues are
totally ordered in time, which Policy v1 relies on to tell whether a steering
control has been acted on yet.
"""

from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, List, Optional, Sequence

from src.intentune.domain.library import TrackNotFound
from src.intentune.domain.models import ListeningContext, Recommendation
from src.intentune.domain.session import (
    InvalidSessionTransition,
    ListenerProfileNotFound,
    ListeningSession,
    OccurrenceStatus,
    RecommendationOccurrence,
    RecommendationOccurrenceNotFound,
    SessionEndReason,
    SessionHistory,
    SessionNotFound,
    SessionState,
    SessionTurn,
    TurnKind,
    new_session,
    new_turn,
)
from src.intentune.domain.validation import new_uuid, require_text
from src.intentune.ports.unit_of_work import UnitOfWork

_TURNS_WITHOUT_TARGET = frozenset({TurnKind.SURPRISE_ME, TurnKind.MORE_FAMILIAR, TurnKind.TRY_SOMETHING_DIFFERENT})
_TICK = timedelta(microseconds=1)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionService:
    def __init__(self, unit_of_work: UnitOfWork, clock: Callable[[], datetime] = _utc_now) -> None:
        self._uow = unit_of_work
        self._clock = clock

    # --- Lifecycle ------------------------------------------------------------------

    def start_session(self, listener_profile_id: str, context: ListeningContext) -> SessionState:
        """Start a fresh session with this intent. The listener's previous ACTIVE session, if any, ends."""
        if not isinstance(context, ListeningContext):
            raise ValueError("context must be a ListeningContext")
        now = self._clock()
        with self._uow:
            if self._uow.listener_profiles.get(listener_profile_id) is None:
                raise ListenerProfileNotFound(listener_profile_id)
            previous = self._uow.listening_sessions.get_active_for_listener(listener_profile_id)
            if previous is not None:
                self._end(previous, SessionEndReason.REPLACED_BY_NEW_SESSION, self._time_after(previous))
            session = new_session(listener_profile_id, context, now)
            self._uow.listening_sessions.add(session)
            self._uow.session_turns.add(new_turn(session, 1, TurnKind.INITIAL_INTENT, context, now))
            self._uow.commit()
        return SessionState(session=session, playing=None, queue=())

    def end_session(self, session_id: str) -> ListeningSession:
        with self._uow:
            session = self._require_active(session_id)
            ended = self._end(session, SessionEndReason.ENDED_BY_LISTENER, self._time_after(session))
            self._uow.commit()
        return ended

    def end_sessions_from_previous_run(self) -> int:
        """End every session a previous run left ACTIVE (D35). Call at startup. Returns how many ended."""
        with self._uow:
            active = self._uow.listening_sessions.list_active()
            for session in active:
                self._end(session, SessionEndReason.APP_RESTARTED, self._time_after(session))
            if active:
                self._uow.commit()
        return len(active)

    # --- Steering ---------------------------------------------------------------------

    def apply_turn(
        self,
        session_id: str,
        kind: TurnKind,
        context: Optional[ListeningContext] = None,
        occurrence_id: Optional[str] = None,
    ) -> SessionTurn:
        kind = TurnKind(kind)
        if kind is TurnKind.INITIAL_INTENT:
            raise InvalidSessionTransition("A session's initial intent is set when the session starts.")
        if (kind is TurnKind.REFINE) != (context is not None):
            raise ValueError("A REFINE turn carries the new context, and only a REFINE turn does.")
        if kind in _TURNS_WITHOUT_TARGET and occurrence_id is not None:
            raise ValueError(f"A {kind.value} turn is not about a single recommendation.")

        with self._uow:
            session = self._require_active(session_id)
            now = self._time_after(session)
            playing = self._playing(session_id)
            target = None
            if kind is TurnKind.REFINE:
                session = session.with_context(context, now)
            elif kind is TurnKind.NEXT:
                if occurrence_id is not None and (playing is None or playing.occurrence_id != occurrence_id):
                    raise InvalidSessionTransition("NEXT applies to the recommendation that is playing.")
                target = playing.occurrence_id if playing is not None else None
                self._advance(session_id, playing, now)
            elif kind in (TurnKind.NOT_FOR_ME, TurnKind.MORE_LIKE_THIS):
                target = occurrence_id or (playing.occurrence_id if playing is not None else None)
                if target is None:
                    raise InvalidSessionTransition(f"A {kind.value} turn needs a recommendation to apply to.")
                self._require_occurrence(session_id, target)

            if kind is not TurnKind.REFINE:
                session = session.touched(now)
            turns = self._uow.session_turns.list_for_session(session_id)
            turn = new_turn(session, turns[-1].sequence + 1, kind, session.current_context, now, occurrence_id=target)
            self._uow.session_turns.add(turn)
            self._uow.listening_sessions.save(session)
            self._uow.commit()
        return turn

    # --- Queue and playback -----------------------------------------------------------

    def queue_recommendations(
        self,
        session_id: str,
        recommendations: Sequence[Recommendation],
        algorithm: str,
        exploration_track_ids: Iterable[str] = (),
    ) -> SessionState:
        """Surface recommendations, in this order, as the session's upcoming queue.

        Each recommendation's candidate_id must be a library track id. rank is
        the algorithm's rank (its position in this list when unset), and score
        is its normalized score. Queue order is the list order, which may
        differ from rank order (for example when #2 is chosen to play first,
        B5). Each occurrence keeps its list position as surfaced_position for
        good. exploration_track_ids marks which of them are exploration picks.
        """
        algorithm = require_text(algorithm, "algorithm")
        recommendations = list(recommendations)
        if not all(isinstance(recommendation, Recommendation) for recommendation in recommendations):
            raise ValueError("recommendations must be Recommendation objects")
        track_ids = [recommendation.candidate.candidate_id for recommendation in recommendations]
        if len(set(track_ids)) != len(track_ids):
            raise ValueError("A queue lists each track at most once.")
        exploration = frozenset(exploration_track_ids)
        if not exploration <= set(track_ids):
            raise ValueError("Exploration picks must be among the queued recommendations.")

        with self._uow:
            session = self._require_active(session_id)
            now = self._time_after(session)
            for track_id in track_ids:
                if self._uow.tracks.get(track_id) is None:
                    raise TrackNotFound(track_id)
            for still_queued in self._uow.recommendation_occurrences.list_for_session(session_id, OccurrenceStatus.QUEUED):
                self._uow.recommendation_occurrences.save(still_queued.replaced(now))
            for position, recommendation in enumerate(recommendations):
                self._uow.recommendation_occurrences.add(
                    RecommendationOccurrence(
                        occurrence_id=new_uuid(),
                        session_id=session_id,
                        track_id=recommendation.candidate.candidate_id,
                        rank=recommendation.rank if recommendation.rank is not None else position + 1,
                        algorithm=algorithm,
                        status=OccurrenceStatus.QUEUED,
                        surfaced_at=now,
                        updated_at=now,
                        score=recommendation.score_breakdown.normalized_score,
                        surfaced_position=position,
                        queue_position=position,
                        is_exploration=recommendation.candidate.candidate_id in exploration,
                    )
                )
            self._uow.listening_sessions.save(session.touched(now))
            state = self._state(session_id)
            self._uow.commit()
        return state

    def play(self, session_id: str, occurrence_id: str) -> SessionState:
        """Start a specific queued recommendation. The one playing before, if any, has been played."""
        with self._uow:
            session = self._require_active(session_id)
            now = self._time_after(session)
            occurrence = self._require_occurrence(session_id, occurrence_id)
            if occurrence.status is not OccurrenceStatus.QUEUED:
                raise InvalidSessionTransition("Only a queued recommendation can start playing.")
            playing = self._playing(session_id)
            if playing is not None:
                self._uow.recommendation_occurrences.save(playing.finished_playing(now))
            self._uow.recommendation_occurrences.save(occurrence.started_playing(now))
            self._uow.listening_sessions.save(session.touched(now))
            state = self._state(session_id)
            self._uow.commit()
        return state

    def advance(self, session_id: str) -> SessionState:
        """Finish the current recommendation, if any, and start the next queued one, if any."""
        with self._uow:
            session = self._require_active(session_id)
            now = self._time_after(session)
            self._advance(session_id, self._playing(session_id), now)
            self._uow.listening_sessions.save(session.touched(now))
            state = self._state(session_id)
            self._uow.commit()
        return state

    # --- Reading ------------------------------------------------------------------

    def get_session(self, session_id: str) -> SessionState:
        with self._uow:
            self._require_session(session_id)
            return self._state(session_id)

    def list_sessions(self, listener_profile_id: str) -> List[ListeningSession]:
        """The listener's sessions, newest first."""
        with self._uow:
            return self._uow.listening_sessions.list_for_listener(listener_profile_id)

    def history(self, session_id: str) -> SessionHistory:
        with self._uow:
            session = self._require_session(session_id)
            return SessionHistory(
                session=session,
                turns=tuple(self._uow.session_turns.list_for_session(session_id)),
                occurrences=tuple(self._uow.recommendation_occurrences.list_for_session(session_id)),
                feedback_events=tuple(self._uow.feedback_events.list_for_session(session_id)),
            )

    # --- Internals (inside the caller's transaction) -----------------------------------

    def _time_after(self, session: ListeningSession) -> datetime:
        """The clock, but strictly later than the session's last change.

        Every change to a session moves its updated_at, so its turns, surfaced
        queues, and playback changes get strictly increasing times even when the
        clock has not moved; this machine's clock advances in about 1 ms steps.
        Within a session, "after" is then exact: a refresh that follows a turn is
        later than it, and two queues are never surfaced at the same moment.
        """
        now = self._clock()
        return now if now > session.updated_at else session.updated_at + _TICK

    def _require_session(self, session_id: str) -> ListeningSession:
        session = self._uow.listening_sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        return session

    def _require_active(self, session_id: str) -> ListeningSession:
        session = self._require_session(session_id)
        if not session.is_active:
            raise InvalidSessionTransition("The session has ended. Start a new session to keep listening.")
        return session

    def _require_occurrence(self, session_id: str, occurrence_id: str) -> RecommendationOccurrence:
        occurrence = self._uow.recommendation_occurrences.get(occurrence_id)
        if occurrence is None or occurrence.session_id != session_id:
            raise RecommendationOccurrenceNotFound(occurrence_id)
        return occurrence

    def _playing(self, session_id: str) -> Optional[RecommendationOccurrence]:
        playing = self._uow.recommendation_occurrences.list_for_session(session_id, OccurrenceStatus.PLAYING)
        return playing[0] if playing else None

    def _advance(self, session_id: str, playing: Optional[RecommendationOccurrence], now: datetime) -> None:
        if playing is not None:
            self._uow.recommendation_occurrences.save(playing.finished_playing(now))
        queue = self._uow.recommendation_occurrences.list_for_session(session_id, OccurrenceStatus.QUEUED)
        if queue:
            self._uow.recommendation_occurrences.save(queue[0].started_playing(now))

    def _end(self, session: ListeningSession, reason: SessionEndReason, now: datetime) -> ListeningSession:
        for occurrence in self._uow.recommendation_occurrences.list_for_session(session.session_id, OccurrenceStatus.QUEUED):
            self._uow.recommendation_occurrences.save(occurrence.discarded(now))
        playing = self._playing(session.session_id)
        if playing is not None:
            self._uow.recommendation_occurrences.save(playing.finished_playing(now))
        ended = session.ended(reason, now)
        self._uow.listening_sessions.save(ended)
        return ended

    def _state(self, session_id: str) -> SessionState:
        return SessionState(
            session=self._require_session(session_id),
            playing=self._playing(session_id),
            queue=tuple(self._uow.recommendation_occurrences.list_for_session(session_id, OccurrenceStatus.QUEUED)),
        )
