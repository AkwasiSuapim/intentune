"""Listening sessions: start, read, steer, and feedback (B8).

Every command answers with the session as it stands after the queue was
re-ranked. Listening begins with a `next` turn while nothing plays ("Play"):
it starts the first queued track. Sessions belong to the local listener (D01).

Feedback travels two ways:
- playback-events: how a track's playback ended (skip or complete, with the
  seconds played and the track's duration);
- reactions: like, save, replay, or not for me, about one recommendation.
A playlist add is feedback too, recorded by the playlist items route.
"""

from fastapi import APIRouter

from src.intentune.api import views
from src.intentune.api.container import Container
from src.intentune.api.dependencies import DEFAULT_LIMIT, ERROR_RESPONSES, ContainerDep, Limit, Offset
from src.intentune.api.schemas import (
    FeedbackOut,
    PlaybackEventIn,
    ReactionIn,
    SessionDetailOut,
    SessionPageOut,
    SessionStateOut,
    StartSessionIn,
    TurnIn,
    TurnResultOut,
)
from src.intentune.application.feedback import FeedbackOutcome
from src.intentune.domain.session import FeedbackEventType, SessionState, TurnKind

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"], responses=ERROR_RESPONSES)


def _state_out(container: Container, state: SessionState) -> SessionStateOut:
    return views.session_state_out(state, container.library().get_tracks(views.track_ids_of(state)))


def _feedback_out(container: Container, outcome: FeedbackOutcome) -> FeedbackOut:
    return views.feedback_out(outcome, container.library().get_tracks(views.track_ids_of(outcome.state)))


@router.post("", response_model=SessionStateOut, status_code=201)
def start_session(body: StartSessionIn, container: ContainerDep) -> SessionStateOut:
    """Start a session with this intent. The listener's previous active session ends. Nothing plays yet."""
    state = container.listening().start(container.listener_profile_id, body.context.to_domain())
    return _state_out(container, state)


@router.get("", response_model=SessionPageOut)
def list_sessions(container: ContainerDep, limit: Limit = DEFAULT_LIMIT, offset: Offset = 0) -> SessionPageOut:
    """The listener's sessions, newest first."""
    sessions = container.sessions().list_sessions(container.listener_profile_id)
    return SessionPageOut(**views.page(sessions, limit, offset, views.session_out))


@router.get("/{session_id}", response_model=SessionDetailOut)
def get_session(session_id: str, container: ContainerDep) -> SessionDetailOut:
    sessions = container.sessions()
    state = sessions.get_session(session_id)
    history = sessions.history(session_id)
    tracks = container.library().get_tracks(views.track_ids_of(state, history))
    return views.session_detail_out(state, history, tracks)


@router.post("/{session_id}/turns", response_model=TurnResultOut)
def apply_turn(session_id: str, body: TurnIn, container: ContainerDep) -> TurnResultOut:
    context = body.context.to_domain() if body.context is not None else None
    turn, state = container.listening().steer(
        session_id, TurnKind(body.kind.upper()), context=context, occurrence_id=body.occurrence_id
    )
    return TurnResultOut(turn=views.turn_out(turn), state=_state_out(container, state))


@router.post("/{session_id}/playback-events", response_model=FeedbackOut, status_code=201)
def report_playback(session_id: str, body: PlaybackEventIn, container: ContainerDep) -> FeedbackOut:
    outcome = container.feedback().report_playback(
        session_id,
        body.occurrence_id,
        FeedbackEventType(body.event_type.upper()),
        body.played_seconds,
        body.duration_seconds,
    )
    return _feedback_out(container, outcome)


@router.post("/{session_id}/recommendations/{occurrence_id}/reactions", response_model=FeedbackOut, status_code=201)
def react(session_id: str, occurrence_id: str, body: ReactionIn, container: ContainerDep) -> FeedbackOut:
    outcome = container.feedback().react(session_id, occurrence_id, FeedbackEventType(body.reaction.upper()))
    return _feedback_out(container, outcome)
