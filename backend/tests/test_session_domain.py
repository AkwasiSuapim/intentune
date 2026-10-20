"""Session domain rules: lifecycle and invariants of sessions, turns, occurrences, and raw feedback events."""

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.intentune.domain.models import ListeningContext
from src.intentune.domain.session import (
    FeedbackEvent,
    FeedbackEventType,
    InvalidSessionTransition,
    ListeningSession,
    OccurrenceStatus,
    RecommendationOccurrence,
    SessionEndReason,
    SessionStatus,
    SessionTurn,
    TurnKind,
    new_session,
    new_turn,
)

_NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
_LATER = _NOW + timedelta(minutes=3)
_LISTENER = "3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e"
_TRACK = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"
_OCCURRENCE = "1b2c3d4e-5f60-4a71-8b92-a3b4c5d6e7f8"
_CONTEXT = ListeningContext(listening_goal="focus", target_energy=0.3, temporary_genres=("ambient",))


def _session(**overrides):
    return replace(new_session(_LISTENER, _CONTEXT, _NOW), **overrides)


def _occurrence(**overrides):
    values = dict(
        occurrence_id=_OCCURRENCE,
        session_id=_session().session_id,
        track_id=_TRACK,
        rank=1,
        algorithm="test-algorithm-v1",
        status=OccurrenceStatus.QUEUED,
        surfaced_at=_NOW,
        updated_at=_NOW,
        score=0.8,
        queue_position=0,
    )
    values.update(overrides)
    return RecommendationOccurrence(**values)


def _event(**overrides):
    values = dict(
        event_id=_OCCURRENCE,
        session_id=_session().session_id,
        occurrence_id=_OCCURRENCE,
        event_type=FeedbackEventType.LIKE,
        occurred_at=_NOW,
    )
    values.update(overrides)
    return FeedbackEvent(**values)


# --- Sessions ------------------------------------------------------------------------


def test_a_new_session_is_active_with_its_context():
    session = new_session(_LISTENER, _CONTEXT, _NOW)

    assert (session.status, session.is_active, session.current_context) == (SessionStatus.ACTIVE, True, _CONTEXT)
    assert (session.started_at, session.updated_at, session.ended_at, session.end_reason) == (_NOW, _NOW, None, None)


def test_ending_a_session_records_when_and_why():
    ended = _session().ended(SessionEndReason.APP_RESTARTED, _LATER)

    assert (ended.status, ended.end_reason, ended.ended_at, ended.updated_at) == (SessionStatus.ENDED, SessionEndReason.APP_RESTARTED, _LATER, _LATER)
    with pytest.raises(InvalidSessionTransition):
        ended.ended(SessionEndReason.ENDED_BY_LISTENER, _LATER)


@pytest.mark.parametrize(
    "overrides",
    [
        dict(status=SessionStatus.ENDED),
        dict(ended_at=_NOW),
        dict(end_reason=SessionEndReason.ENDED_BY_LISTENER),
        dict(status=SessionStatus.ENDED, ended_at=_NOW),
        dict(current_context={"target_energy": 0.3}),
        dict(listener_profile_id="listener"),
    ],
)
def test_session_invariants(overrides):
    with pytest.raises(ValueError):
        _session(**overrides)


def test_with_context_replaces_the_intent():
    refined = ListeningContext(target_energy=0.8)

    session = _session().with_context(refined, _LATER)

    assert (session.current_context, session.updated_at) == (refined, _LATER)


# --- Turns -----------------------------------------------------------------------------


def test_the_first_turn_and_only_the_first_is_the_initial_intent():
    session = _session()

    assert new_turn(session, 1, TurnKind.INITIAL_INTENT, _CONTEXT, _NOW).sequence == 1
    with pytest.raises(ValueError):
        new_turn(session, 2, TurnKind.INITIAL_INTENT, _CONTEXT, _NOW)
    with pytest.raises(ValueError):
        new_turn(session, 1, TurnKind.REFINE, _CONTEXT, _NOW)
    with pytest.raises(ValueError):
        new_turn(session, 0, TurnKind.INITIAL_INTENT, _CONTEXT, _NOW)


@pytest.mark.parametrize("kind", [TurnKind.NOT_FOR_ME, TurnKind.MORE_LIKE_THIS])
def test_turns_about_a_recommendation_name_it(kind):
    session = _session()

    turn = new_turn(session, 2, kind, _CONTEXT, _NOW, occurrence_id=_OCCURRENCE)

    assert turn.is_about_an_occurrence
    with pytest.raises(ValueError):
        new_turn(session, 2, kind, _CONTEXT, _NOW)


@pytest.mark.parametrize("kind", [TurnKind.INITIAL_INTENT, TurnKind.REFINE])
def test_intent_turns_are_not_about_a_recommendation(kind):
    sequence = 1 if kind is TurnKind.INITIAL_INTENT else 2
    with pytest.raises(ValueError):
        new_turn(_session(), sequence, kind, _CONTEXT, _NOW, occurrence_id=_OCCURRENCE)


def test_a_turn_stores_structured_context_only():
    with pytest.raises(ValueError):
        SessionTurn(_OCCURRENCE, _session().session_id, 2, TurnKind.REFINE, "play something calmer", _NOW)


# --- Occurrences -------------------------------------------------------------------------


def test_occurrence_lifecycle_queued_playing_played():
    playing = _occurrence().started_playing(_NOW + timedelta(seconds=1))
    played = playing.finished_playing(_LATER)

    assert (playing.status, playing.queue_position, playing.has_started) == (OccurrenceStatus.PLAYING, None, True)
    assert (played.status, played.finished_at) == (OccurrenceStatus.PLAYED, _LATER)


@pytest.mark.parametrize("transition, status", [("replaced", OccurrenceStatus.REPLACED), ("discarded", OccurrenceStatus.DISCARDED)])
def test_a_queued_occurrence_can_leave_the_queue_without_playing(transition, status):
    left = getattr(_occurrence(), transition)(_LATER)

    assert (left.status, left.queue_position, left.started_at, left.finished_at) == (status, None, None, _LATER)


@pytest.mark.parametrize(
    "start, transition",
    [
        ("playing", "started_playing"),
        ("queued", "finished_playing"),
        ("playing", "replaced"),
        ("played", "discarded"),
        ("played", "started_playing"),
    ],
)
def test_impossible_occurrence_transitions_are_refused(start, transition):
    occurrence = _occurrence()
    if start in ("playing", "played"):
        occurrence = occurrence.started_playing(_NOW)
    if start == "played":
        occurrence = occurrence.finished_playing(_NOW)

    with pytest.raises(InvalidSessionTransition):
        getattr(occurrence, transition)(_LATER)


@pytest.mark.parametrize(
    "overrides",
    [
        dict(queue_position=None),
        dict(status=OccurrenceStatus.PLAYING),
        dict(status=OccurrenceStatus.PLAYED, queue_position=None, started_at=_NOW),
        dict(status=OccurrenceStatus.REPLACED, queue_position=None),
        dict(rank=0),
        dict(score=1.5),
        dict(score=-0.1),
        dict(algorithm=" "),
        dict(track_id="1"),
    ],
)
def test_occurrence_invariants(overrides):
    with pytest.raises(ValueError):
        _occurrence(**overrides)


def test_an_occurrence_may_have_no_score():
    assert _occurrence(score=None).score is None


# --- Feedback events ------------------------------------------------------------------------


def test_a_feedback_event_derives_the_played_fraction():
    event = _event(event_type=FeedbackEventType.SKIP, played_seconds=12, duration_seconds=200)

    assert event.played_fraction == pytest.approx(0.06)
    assert (event.played_seconds, event.duration_seconds) == (12.0, 200.0)


def test_the_played_fraction_is_capped_when_the_clock_runs_past_the_duration():
    assert _event(event_type=FeedbackEventType.COMPLETE, played_seconds=201.5, duration_seconds=200).played_fraction == 1.0


def test_a_reaction_may_carry_no_playback_facts():
    event = _event(event_type=FeedbackEventType.NOT_FOR_ME)

    assert (event.played_seconds, event.duration_seconds, event.played_fraction) == (None, None, None)


@pytest.mark.parametrize("event_type", [FeedbackEventType.SKIP, FeedbackEventType.COMPLETE])
def test_skip_and_complete_record_the_playback_facts(event_type):
    with pytest.raises(ValueError):
        _event(event_type=event_type)
    with pytest.raises(ValueError):
        _event(event_type=event_type, played_seconds=10)


@pytest.mark.parametrize(
    "played, duration",
    [(-1, 200), (10, 0), (10, -5), (math.nan, 200), (10, math.inf), (True, 200), (10, None), (None, 200)],
)
def test_playback_facts_must_be_sensible(played, duration):
    with pytest.raises(ValueError):
        _event(event_type=FeedbackEventType.LIKE, played_seconds=played, duration_seconds=duration)


def test_unknown_event_types_are_refused():
    with pytest.raises(ValueError):
        _event(event_type="PROGRESS_TICK")
