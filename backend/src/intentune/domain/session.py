"""Listening sessions (Prototype 1, phase B4): where the listener is now, and how they got here.

A ListeningSession is one listening experience, not a chat thread (spec §10).
It owns the current state (D31): whether it is active, and the structured
ListeningContext in force (D29). Its current track and its upcoming queue are
its RecommendationOccurrences that are PLAYING and QUEUED.

History is recorded separately and never rewritten:

- SessionTurn: each steering action (initial intent, refine, next, not for
  me, ...), with the context it left in force. No raw conversational text is
  ever stored (D33).
- RecommendationOccurrence: a Recommendation (an algorithm result, see
  domain/models.py) surfaced in this session at a moment: which track, at
  which rank and score, from which algorithm, and what became of it. The two
  stay distinct: a Recommendation is computed; an occurrence is a fact.
- FeedbackEvent: a raw listening fact, for example "skipped after 12 of 200
  seconds". B4 defines it; recording events and interpreting them (Feedback
  Policy v1) are B6.

No UI-only state (drawers, composer drafts, animation) belongs here (D32).

Session lifecycle:

    start -> ACTIVE -> ENDED   (ENDED_BY_LISTENER, REPLACED_BY_NEW_SESSION, or APP_RESTARTED)

A listener has at most one ACTIVE session. Sessions are never resumed after a
restart: they end, and the next listening action starts a fresh one (D35).

Occurrence lifecycle:

    QUEUED -> PLAYING -> PLAYED
    QUEUED -> REPLACED    (a newer queue took its place before it played)
    QUEUED -> DISCARDED   (the session ended first)

Pure: no database, HTTP, or file code.
"""

import math
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

from src.intentune.domain.models import ListeningContext
from src.intentune.domain.validation import (
    new_uuid,
    optional_utc_datetime,
    require_canonical_uuid,
    require_non_negative_int,
    require_text,
    require_utc_datetime,
)


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class SessionEndReason(str, Enum):
    ENDED_BY_LISTENER = "ENDED_BY_LISTENER"
    REPLACED_BY_NEW_SESSION = "REPLACED_BY_NEW_SESSION"
    APP_RESTARTED = "APP_RESTARTED"


class TurnKind(str, Enum):
    """The steering actions of spec §24. Their effect on ranking (exploration, exclusion, affinity) is B5/B6."""

    INITIAL_INTENT = "INITIAL_INTENT"
    REFINE = "REFINE"
    NEXT = "NEXT"
    NOT_FOR_ME = "NOT_FOR_ME"
    MORE_LIKE_THIS = "MORE_LIKE_THIS"
    SURPRISE_ME = "SURPRISE_ME"
    MORE_FAMILIAR = "MORE_FAMILIAR"
    TRY_SOMETHING_DIFFERENT = "TRY_SOMETHING_DIFFERENT"


_TURNS_ABOUT_AN_OCCURRENCE = frozenset({TurnKind.NOT_FOR_ME, TurnKind.MORE_LIKE_THIS})


class OccurrenceStatus(str, Enum):
    QUEUED = "QUEUED"
    PLAYING = "PLAYING"
    PLAYED = "PLAYED"
    REPLACED = "REPLACED"
    DISCARDED = "DISCARDED"


class FeedbackEventType(str, Enum):
    """The raw listening facts of execution guide §9, PLAYLIST_ADD (B7): a recommendation added to a playlist,
    and UNLIKE (B9): the listener took back a Like. UNLIKE is a fact of its own; the LIKE it cancels stays stored."""

    LIKE = "LIKE"
    SAVE = "SAVE"
    REPLAY = "REPLAY"
    SKIP = "SKIP"
    COMPLETE = "COMPLETE"
    NOT_FOR_ME = "NOT_FOR_ME"
    PLAYLIST_ADD = "PLAYLIST_ADD"
    UNLIKE = "UNLIKE"


_EVENTS_WITH_PLAYBACK_FACTS = frozenset({FeedbackEventType.SKIP, FeedbackEventType.COMPLETE})

# The algorithm label of an occurrence the listener chose to hear again (B6): no algorithm surfaced it.
LISTENER_REPLAY_ALGORITHM = "listener-replay"


# --- Errors ----------------------------------------------------------------------


class SessionError(Exception):
    """Base class for session errors the application layer reports to its callers."""


class SessionNotFound(SessionError, LookupError):
    pass


class RecommendationOccurrenceNotFound(SessionError, LookupError):
    """No such occurrence in this session (API code RECOMMENDATION_NOT_FOUND)."""


class ListenerProfileNotFound(SessionError, LookupError):
    pass


class InvalidSessionTransition(SessionError, ValueError):
    """The command is not allowed in the session's current state (API code INVALID_SESSION_TRANSITION)."""


# --- Entities ------------------------------------------------------------------------


def _require_context(value: object) -> ListeningContext:
    if not isinstance(value, ListeningContext):
        raise ValueError("context must be a ListeningContext")
    return value


@dataclass(frozen=True)
class ListeningSession:
    session_id: str
    listener_profile_id: str
    status: SessionStatus
    current_context: ListeningContext
    started_at: datetime
    updated_at: datetime
    ended_at: Optional[datetime] = None
    end_reason: Optional[SessionEndReason] = None

    def __post_init__(self) -> None:
        require_canonical_uuid(self.session_id, "session_id")
        require_canonical_uuid(self.listener_profile_id, "listener_profile_id")
        object.__setattr__(self, "status", SessionStatus(self.status))
        _require_context(self.current_context)
        object.__setattr__(self, "started_at", require_utc_datetime(self.started_at, "started_at"))
        object.__setattr__(self, "updated_at", require_utc_datetime(self.updated_at, "updated_at"))
        object.__setattr__(self, "ended_at", optional_utc_datetime(self.ended_at, "ended_at"))
        if self.end_reason is not None:
            object.__setattr__(self, "end_reason", SessionEndReason(self.end_reason))
        ended = self.status is SessionStatus.ENDED
        if ended != (self.ended_at is not None) or ended != (self.end_reason is not None):
            raise ValueError("an ENDED session has ended_at and end_reason; an ACTIVE one has neither")

    @property
    def is_active(self) -> bool:
        return self.status is SessionStatus.ACTIVE

    def with_context(self, context: ListeningContext, now: datetime) -> "ListeningSession":
        return replace(self, current_context=_require_context(context), updated_at=now)

    def touched(self, now: datetime) -> "ListeningSession":
        return replace(self, updated_at=now)

    def ended(self, reason: SessionEndReason, now: datetime) -> "ListeningSession":
        if not self.is_active:
            raise InvalidSessionTransition("The session has already ended.")
        return replace(self, status=SessionStatus.ENDED, end_reason=reason, ended_at=now, updated_at=now)


def new_session(listener_profile_id: str, context: ListeningContext, now: datetime) -> ListeningSession:
    return ListeningSession(
        session_id=new_uuid(),
        listener_profile_id=listener_profile_id,
        status=SessionStatus.ACTIVE,
        current_context=context,
        started_at=now,
        updated_at=now,
    )


@dataclass(frozen=True)
class SessionTurn:
    """One steering action. context is the ListeningContext in force after the turn."""

    turn_id: str
    session_id: str
    sequence: int
    kind: TurnKind
    context: ListeningContext
    created_at: datetime
    occurrence_id: Optional[str] = None

    def __post_init__(self) -> None:
        require_canonical_uuid(self.turn_id, "turn_id")
        require_canonical_uuid(self.session_id, "session_id")
        require_non_negative_int(self.sequence, "sequence")
        object.__setattr__(self, "kind", TurnKind(self.kind))
        _require_context(self.context)
        object.__setattr__(self, "created_at", require_utc_datetime(self.created_at, "created_at"))
        if self.occurrence_id is not None:
            require_canonical_uuid(self.occurrence_id, "occurrence_id")
        if self.sequence < 1:
            raise ValueError("turn sequences start at 1")
        if (self.kind is TurnKind.INITIAL_INTENT) != (self.sequence == 1):
            raise ValueError("the first turn, and only the first, is INITIAL_INTENT")
        if self.kind in _TURNS_ABOUT_AN_OCCURRENCE and self.occurrence_id is None:
            raise ValueError(f"a {self.kind.value} turn names the occurrence it is about")
        if self.kind in (TurnKind.INITIAL_INTENT, TurnKind.REFINE) and self.occurrence_id is not None:
            raise ValueError(f"a {self.kind.value} turn is about the intent, not an occurrence")

    @property
    def is_about_an_occurrence(self) -> bool:
        return self.kind in _TURNS_ABOUT_AN_OCCURRENCE


def new_turn(
    session: ListeningSession,
    sequence: int,
    kind: TurnKind,
    context: ListeningContext,
    now: datetime,
    occurrence_id: Optional[str] = None,
) -> SessionTurn:
    return SessionTurn(
        turn_id=new_uuid(),
        session_id=session.session_id,
        sequence=sequence,
        kind=kind,
        context=context,
        created_at=now,
        occurrence_id=occurrence_id,
    )


def _optional_unit_score(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
        raise ValueError("score must be a number from 0.0 to 1.0")
    return float(value)


@dataclass(frozen=True)
class RecommendationOccurrence:
    """A recommendation surfaced in a session. rank and score are as the algorithm produced them.

    is_exploration marks a deliberate exploration pick (B5), so how exploration
    went can be judged from later evidence.

    surfaced_position (B5) is where in its queue the occurrence was surfaced,
    from 0, and never changes. queue_position is the current queue state and is
    cleared when the occurrence leaves the queue, so only surfaced_position can
    reconstruct a surfaced order, such as rank 2 queued ahead of rank 1.
    """

    occurrence_id: str
    session_id: str
    track_id: str
    rank: int
    algorithm: str
    status: OccurrenceStatus
    surfaced_at: datetime
    updated_at: datetime
    surfaced_position: int
    score: Optional[float] = None
    queue_position: Optional[int] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    is_exploration: bool = False

    def __post_init__(self) -> None:
        require_canonical_uuid(self.occurrence_id, "occurrence_id")
        require_canonical_uuid(self.session_id, "session_id")
        require_canonical_uuid(self.track_id, "track_id")
        require_non_negative_int(self.rank, "rank")
        if self.rank < 1:
            raise ValueError("rank starts at 1")
        object.__setattr__(self, "algorithm", require_text(self.algorithm, "algorithm"))
        object.__setattr__(self, "status", OccurrenceStatus(self.status))
        object.__setattr__(self, "surfaced_at", require_utc_datetime(self.surfaced_at, "surfaced_at"))
        object.__setattr__(self, "updated_at", require_utc_datetime(self.updated_at, "updated_at"))
        require_non_negative_int(self.surfaced_position, "surfaced_position")
        object.__setattr__(self, "score", _optional_unit_score(self.score))
        if self.queue_position is not None:
            require_non_negative_int(self.queue_position, "queue_position")
        object.__setattr__(self, "started_at", optional_utc_datetime(self.started_at, "started_at"))
        object.__setattr__(self, "finished_at", optional_utc_datetime(self.finished_at, "finished_at"))
        if not isinstance(self.is_exploration, bool):
            raise ValueError("is_exploration must be a bool")

        queued = self.status is OccurrenceStatus.QUEUED
        if queued != (self.queue_position is not None):
            raise ValueError("an occurrence has a queue_position exactly while it is QUEUED")
        has_played = self.status in (OccurrenceStatus.PLAYING, OccurrenceStatus.PLAYED)
        if has_played != (self.started_at is not None):
            raise ValueError("an occurrence has started_at exactly when it is PLAYING or PLAYED")
        finished = self.status in (OccurrenceStatus.PLAYED, OccurrenceStatus.REPLACED, OccurrenceStatus.DISCARDED)
        if finished != (self.finished_at is not None):
            raise ValueError("an occurrence has finished_at exactly when it is PLAYED, REPLACED, or DISCARDED")

    @property
    def has_started(self) -> bool:
        return self.started_at is not None

    @property
    def is_listener_replay(self) -> bool:
        return self.algorithm == LISTENER_REPLAY_ALGORITHM

    def replayed(self, occurrence_id: str, now: datetime) -> "RecommendationOccurrence":
        """A fresh occurrence of this track, playing from now, because the listener asked to hear it again (B6).

        The listener chose it, not an algorithm: it carries the listener-replay label,
        rank 1, and no score. This occurrence keeps its own history.
        """
        if not self.has_started:
            raise InvalidSessionTransition("Only a recommendation that has played can be replayed.")
        return RecommendationOccurrence(
            occurrence_id=occurrence_id,
            session_id=self.session_id,
            track_id=self.track_id,
            rank=1,
            algorithm=LISTENER_REPLAY_ALGORITHM,
            status=OccurrenceStatus.PLAYING,
            surfaced_at=now,
            updated_at=now,
            surfaced_position=0,
            started_at=now,
        )

    def started_playing(self, now: datetime) -> "RecommendationOccurrence":
        self._require(OccurrenceStatus.QUEUED, "Only a queued recommendation can start playing.")
        return replace(self, status=OccurrenceStatus.PLAYING, queue_position=None, started_at=now, updated_at=now)

    def finished_playing(self, now: datetime) -> "RecommendationOccurrence":
        self._require(OccurrenceStatus.PLAYING, "Only the playing recommendation can finish playing.")
        return replace(self, status=OccurrenceStatus.PLAYED, finished_at=now, updated_at=now)

    def replaced(self, now: datetime) -> "RecommendationOccurrence":
        self._require(OccurrenceStatus.QUEUED, "Only a queued recommendation can be replaced.")
        return replace(self, status=OccurrenceStatus.REPLACED, queue_position=None, finished_at=now, updated_at=now)

    def discarded(self, now: datetime) -> "RecommendationOccurrence":
        self._require(OccurrenceStatus.QUEUED, "Only a queued recommendation can be discarded.")
        return replace(self, status=OccurrenceStatus.DISCARDED, queue_position=None, finished_at=now, updated_at=now)

    def _require(self, status: OccurrenceStatus, message: str) -> None:
        if self.status is not status:
            raise InvalidSessionTransition(message)


def _optional_seconds(value: object, field_name: str, positive: bool = False) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{field_name} must be {'positive' if positive else 'non-negative'}")
    return float(value)


@dataclass(frozen=True)
class FeedbackEvent:
    """A raw listening fact (spec §9). It records what happened, never what it is taken to mean.

    SKIP and COMPLETE carry played_seconds and duration_seconds. played_fraction
    is derived from them: played_seconds / duration_seconds, capped at 1.0,
    because a player's clock can run slightly past the reported duration.
    """

    event_id: str
    session_id: str
    occurrence_id: str
    event_type: FeedbackEventType
    occurred_at: datetime
    played_seconds: Optional[float] = None
    duration_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        require_canonical_uuid(self.event_id, "event_id")
        require_canonical_uuid(self.session_id, "session_id")
        require_canonical_uuid(self.occurrence_id, "occurrence_id")
        object.__setattr__(self, "event_type", FeedbackEventType(self.event_type))
        object.__setattr__(self, "occurred_at", require_utc_datetime(self.occurred_at, "occurred_at"))
        object.__setattr__(self, "played_seconds", _optional_seconds(self.played_seconds, "played_seconds"))
        object.__setattr__(self, "duration_seconds", _optional_seconds(self.duration_seconds, "duration_seconds", positive=True))
        if self.event_type in _EVENTS_WITH_PLAYBACK_FACTS and (self.played_seconds is None or self.duration_seconds is None):
            raise ValueError(f"a {self.event_type.value} event records played_seconds and duration_seconds")
        if (self.played_seconds is None) != (self.duration_seconds is None):
            raise ValueError("played_seconds and duration_seconds are recorded together")

    @property
    def played_fraction(self) -> Optional[float]:
        if self.played_seconds is None or self.duration_seconds is None:
            return None
        return min(self.played_seconds / self.duration_seconds, 1.0)


# --- Read models -----------------------------------------------------------------------


@dataclass(frozen=True)
class SessionState:
    """Where a session is now: the session, what is playing, and what is queued next (in order)."""

    session: ListeningSession
    playing: Optional[RecommendationOccurrence]
    queue: Tuple[RecommendationOccurrence, ...]


@dataclass(frozen=True)
class SessionHistory:
    """How a session got where it is: every turn, occurrence, and feedback event, in order."""

    session: ListeningSession
    turns: Tuple[SessionTurn, ...]
    occurrences: Tuple[RecommendationOccurrence, ...]
    feedback_events: Tuple[FeedbackEvent, ...]
