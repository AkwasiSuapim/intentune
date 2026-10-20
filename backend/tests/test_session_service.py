"""SessionService application tests: pure use-case tests, no HTTP, against a migrated SQLite database.

Covers the B4 rules of the execution guide (§7): the session owns current
state while turns, occurrences, and feedback hold history; algorithm
Recommendations stay separate from surfaced RecommendationOccurrences; no
raw prompt is stored; and after a restart history is kept, the active queue
is not resumed, and the next listening action starts a fresh session.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.application.sessions import SessionService
from src.intentune.domain.library import AudioFormat, Track, TrackNotFound, TrackStatus
from src.intentune.domain.listener import ListenerProfile
from src.intentune.domain.models import (
    ListeningContext,
    MusicCandidate,
    Recommendation,
    ScoreBreakdown,
    ScoreComponent,
    UserProfile,
)
from src.intentune.domain.ranking import rank_candidates
from src.intentune.domain.session import (
    FeedbackEvent,
    FeedbackEventType,
    InvalidSessionTransition,
    ListenerProfileNotFound,
    OccurrenceStatus,
    RecommendationOccurrenceNotFound,
    SessionEndReason,
    SessionNotFound,
    SessionStatus,
    TurnKind,
)
from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork

_NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
_CALM = ListeningContext(listening_goal="focus", target_energy=0.2, temporary_genres=("ambient",))
_ALGORITHM = "test-algorithm-v1"


class SteppingClock:
    """A clock that advances one second per reading, so every change gets a distinct time."""

    def __init__(self):
        self._now = _NOW

    def __call__(self):
        self._now += timedelta(seconds=1)
        return self._now


@pytest.fixture
def sessions(unit_of_work):
    return SessionService(unit_of_work, clock=SteppingClock())


@pytest.fixture
def listener(unit_of_work):
    return ensure_default_listener(unit_of_work).listener_profile_id


@pytest.fixture
def tracks(unit_of_work):
    created = []
    with unit_of_work:
        for char in "abcdef":
            track = Track(
                track_id=str(uuid.uuid4()),
                sha256=char * 64,
                size_bytes=10,
                audio_format=AudioFormat.FLAC,
                status=TrackStatus.READY,
                original_filename=f"{char}.flac",
                created_at=_NOW,
                updated_at=_NOW,
                analysis_version="test@1",
            )
            unit_of_work.tracks.add(track)
            created.append(track.track_id)
        unit_of_work.commit()
    return created


def _recommendation(track_id, points=8.0, rank=None):
    return Recommendation(
        candidate=MusicCandidate(candidate_id=track_id, title="Song", creator="Artist", source="library"),
        score_breakdown=ScoreBreakdown(
            total_score=points, maximum_score=10.0, components=(ScoreComponent("genre", points, 10.0, "genre match"),)
        ),
        rank=rank,
    )


def _queue(sessions, session_id, track_ids):
    return sessions.queue_recommendations(session_id, [_recommendation(track_id, rank=index + 1) for index, track_id in enumerate(track_ids)], _ALGORITHM)


# --- Starting and ending ---------------------------------------------------------------


def test_start_session_creates_an_active_session_with_its_initial_intent(sessions, listener):
    state = sessions.start_session(listener, _CALM)

    assert (state.session.status, state.session.current_context, state.playing, state.queue) == (SessionStatus.ACTIVE, _CALM, None, ())
    [turn] = sessions.history(state.session.session_id).turns
    assert (turn.sequence, turn.kind, turn.context, turn.occurrence_id) == (1, TurnKind.INITIAL_INTENT, _CALM, None)


def test_start_session_requires_a_known_listener(sessions):
    with pytest.raises(ListenerProfileNotFound):
        sessions.start_session(str(uuid.uuid4()), _CALM)


def test_starting_a_new_session_ends_the_listeners_active_one(sessions, listener, tracks):
    first = sessions.start_session(listener, _CALM).session
    _queue(sessions, first.session_id, tracks[:2])
    sessions.advance(first.session_id)

    second = sessions.start_session(listener, ListeningContext(target_energy=0.9)).session

    old = sessions.get_session(first.session_id)
    assert (old.session.status, old.session.end_reason) == (SessionStatus.ENDED, SessionEndReason.REPLACED_BY_NEW_SESSION)
    assert (old.playing, old.queue) == (None, ())
    assert [occurrence.status for occurrence in sessions.history(first.session_id).occurrences] == [OccurrenceStatus.PLAYED, OccurrenceStatus.DISCARDED]
    assert sessions.get_session(second.session_id).session.is_active
    assert [session.session_id for session in sessions.list_sessions(listener)] == [second.session_id, first.session_id]


def test_end_session_discards_the_queue_and_keeps_history(sessions, listener, tracks):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    _queue(sessions, session_id, tracks[:3])
    sessions.advance(session_id)

    ended = sessions.end_session(session_id)

    assert (ended.status, ended.end_reason) == (SessionStatus.ENDED, SessionEndReason.ENDED_BY_LISTENER)
    history = sessions.history(session_id)
    assert [occurrence.status for occurrence in history.occurrences] == [OccurrenceStatus.PLAYED, OccurrenceStatus.DISCARDED, OccurrenceStatus.DISCARDED]
    assert len(history.turns) == 1


def test_an_ended_session_refuses_every_command_but_can_still_be_read(sessions, listener, tracks):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    occurrence_id = _queue(sessions, session_id, tracks[:1]).queue[0].occurrence_id
    sessions.end_session(session_id)

    for command in (
        lambda: sessions.apply_turn(session_id, TurnKind.SURPRISE_ME),
        lambda: _queue(sessions, session_id, tracks[1:2]),
        lambda: sessions.play(session_id, occurrence_id),
        lambda: sessions.advance(session_id),
        lambda: sessions.end_session(session_id),
    ):
        with pytest.raises(InvalidSessionTransition):
            command()
    assert sessions.get_session(session_id).session.status is SessionStatus.ENDED


def test_unknown_sessions_are_not_found(sessions):
    unknown = str(uuid.uuid4())

    for command in (lambda: sessions.get_session(unknown), lambda: sessions.history(unknown), lambda: sessions.end_session(unknown)):
        with pytest.raises(SessionNotFound):
            command()


# --- Restart (D35) --------------------------------------------------------------------------


def test_after_a_restart_history_is_kept_the_queue_is_not_resumed_and_listening_starts_fresh(migrated_database_url, listener, tracks):
    first_run = create_database_engine(migrated_database_url)
    try:
        before = SessionService(SqlAlchemyUnitOfWork(create_session_factory(first_run)))
        session_id = before.start_session(listener, _CALM).session.session_id
        _queue(before, session_id, tracks[:3])
        before.advance(session_id)
        before.apply_turn(session_id, TurnKind.MORE_FAMILIAR)
    finally:
        first_run.dispose()

    second_run = create_database_engine(migrated_database_url)
    try:
        after = SessionService(SqlAlchemyUnitOfWork(create_session_factory(second_run)))
        assert after.end_sessions_from_previous_run() == 1
        assert after.end_sessions_from_previous_run() == 0

        restarted = after.get_session(session_id)
        assert (restarted.session.status, restarted.session.end_reason) == (SessionStatus.ENDED, SessionEndReason.APP_RESTARTED)
        assert (restarted.playing, restarted.queue) == (None, ())
        history = after.history(session_id)
        assert [turn.kind for turn in history.turns] == [TurnKind.INITIAL_INTENT, TurnKind.MORE_FAMILIAR]
        assert [occurrence.status for occurrence in history.occurrences] == [OccurrenceStatus.PLAYED, OccurrenceStatus.DISCARDED, OccurrenceStatus.DISCARDED]

        fresh = after.start_session(listener, _CALM)
        assert fresh.session.session_id != session_id
        assert (fresh.playing, fresh.queue) == (None, ())
    finally:
        second_run.dispose()


# --- Queue and playback --------------------------------------------------------------------


def test_queued_recommendations_become_occurrences_in_list_order(sessions, listener, tracks):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    recommendations = [_recommendation(tracks[1], points=7.0, rank=2), _recommendation(tracks[0], points=9.0, rank=1)]

    state = sessions.queue_recommendations(session_id, recommendations, _ALGORITHM)

    assert [(occurrence.track_id, occurrence.rank, occurrence.score, occurrence.queue_position) for occurrence in state.queue] == [
        (tracks[1], 2, 0.7, 0),
        (tracks[0], 1, 0.9, 1),
    ]
    assert all((occurrence.algorithm, occurrence.status) == (_ALGORITHM, OccurrenceStatus.QUEUED) for occurrence in state.queue)


def test_canonical_rankings_can_be_surfaced_and_stay_separate_from_their_occurrences(sessions, listener, tracks):
    candidates = [
        MusicCandidate(candidate_id=track_id, title=f"T{index}", creator="A", source="library", genre=genre, mood="calm", energy=energy, danceability=0.3)
        for index, (track_id, genre, energy) in enumerate(zip(tracks[:3], ("ambient", "rock", "ambient"), (0.2, 0.9, 0.5)))
    ]
    ranked = rank_candidates(candidates, UserProfile(preferred_genres=("ambient",), preferred_moods=("calm",), preferred_energy=0.2, preferred_danceability=0.3), limit=3)
    session_id = sessions.start_session(listener, _CALM).session.session_id

    state = sessions.queue_recommendations(session_id, ranked, "legacy-content-v1")

    assert [occurrence.track_id for occurrence in state.queue] == [recommendation.candidate.candidate_id for recommendation in ranked]
    assert [occurrence.rank for occurrence in state.queue] == [1, 2, 3]
    assert [occurrence.score for occurrence in state.queue] == [recommendation.score_breakdown.normalized_score for recommendation in ranked]
    assert all(not isinstance(occurrence, Recommendation) for occurrence in state.queue)


def test_a_new_queue_replaces_what_was_still_queued(sessions, listener, tracks):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    _queue(sessions, session_id, tracks[:3])
    sessions.advance(session_id)

    state = _queue(sessions, session_id, tracks[3:5])

    assert [occurrence.track_id for occurrence in state.queue] == tracks[3:5]
    assert state.playing.track_id == tracks[0]
    statuses = [(occurrence.track_id, occurrence.status) for occurrence in sessions.history(session_id).occurrences]
    assert statuses == [
        (tracks[0], OccurrenceStatus.PLAYING),
        (tracks[1], OccurrenceStatus.REPLACED),
        (tracks[2], OccurrenceStatus.REPLACED),
        (tracks[3], OccurrenceStatus.QUEUED),
        (tracks[4], OccurrenceStatus.QUEUED),
    ]


def test_queueing_an_unknown_track_changes_nothing(sessions, listener, tracks):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    _queue(sessions, session_id, tracks[:2])

    with pytest.raises(TrackNotFound):
        _queue(sessions, session_id, [tracks[2], str(uuid.uuid4())])

    assert [occurrence.track_id for occurrence in sessions.get_session(session_id).queue] == tracks[:2]


def test_a_queue_lists_each_track_once(sessions, listener, tracks):
    session_id = sessions.start_session(listener, _CALM).session.session_id

    with pytest.raises(ValueError):
        _queue(sessions, session_id, [tracks[0], tracks[0]])


def test_advance_plays_the_queue_in_order(sessions, listener, tracks):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    _queue(sessions, session_id, tracks[:2])

    first = sessions.advance(session_id)
    second = sessions.advance(session_id)
    after_the_end = sessions.advance(session_id)

    assert (first.playing.track_id, [occurrence.track_id for occurrence in first.queue]) == (tracks[0], [tracks[1]])
    assert (second.playing.track_id, second.queue) == (tracks[1], ())
    assert (after_the_end.playing, after_the_end.queue) == (None, ())
    assert [occurrence.status for occurrence in sessions.history(session_id).occurrences] == [OccurrenceStatus.PLAYED, OccurrenceStatus.PLAYED]


def test_play_starts_a_chosen_queued_recommendation(sessions, listener, tracks):
    """For example #2 playing before #1 (B5 decides when)."""
    session_id = sessions.start_session(listener, _CALM).session.session_id
    queue = _queue(sessions, session_id, tracks[:3]).queue

    state = sessions.play(session_id, queue[1].occurrence_id)

    assert state.playing.occurrence_id == queue[1].occurrence_id
    assert [occurrence.occurrence_id for occurrence in state.queue] == [queue[0].occurrence_id, queue[2].occurrence_id]
    assert sessions.advance(session_id).playing.occurrence_id == queue[0].occurrence_id


def test_only_queued_recommendations_of_this_session_can_be_played(sessions, listener, tracks):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    first = _queue(sessions, session_id, tracks[:2]).queue[0]
    sessions.play(session_id, first.occurrence_id)

    with pytest.raises(InvalidSessionTransition):
        sessions.play(session_id, first.occurrence_id)
    with pytest.raises(RecommendationOccurrenceNotFound):
        sessions.play(session_id, str(uuid.uuid4()))


# --- Turns ---------------------------------------------------------------------------------


def test_refine_replaces_the_context_and_records_it(sessions, listener):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    livelier = ListeningContext(listening_goal="focus", target_energy=0.6, temporary_genres=("ambient", "electronic"))

    turn = sessions.apply_turn(session_id, TurnKind.REFINE, context=livelier)

    assert (turn.sequence, turn.kind, turn.context) == (2, TurnKind.REFINE, livelier)
    assert sessions.get_session(session_id).session.current_context == livelier
    assert [turn.context for turn in sessions.history(session_id).turns] == [_CALM, livelier]


def test_turn_arguments_are_validated(sessions, listener):
    session_id = sessions.start_session(listener, _CALM).session.session_id

    with pytest.raises(InvalidSessionTransition):
        sessions.apply_turn(session_id, TurnKind.INITIAL_INTENT)
    with pytest.raises(ValueError):
        sessions.apply_turn(session_id, TurnKind.REFINE)
    with pytest.raises(ValueError):
        sessions.apply_turn(session_id, TurnKind.SURPRISE_ME, context=_CALM)
    with pytest.raises(ValueError):
        sessions.apply_turn(session_id, TurnKind.MORE_FAMILIAR, occurrence_id=str(uuid.uuid4()))
    assert len(sessions.history(session_id).turns) == 1


def test_next_finishes_the_current_track_starts_the_next_and_records_what_was_skipped(sessions, listener, tracks):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    _queue(sessions, session_id, tracks[:2])
    skipped = sessions.advance(session_id).playing

    turn = sessions.apply_turn(session_id, TurnKind.NEXT)

    assert (turn.kind, turn.occurrence_id, turn.context) == (TurnKind.NEXT, skipped.occurrence_id, _CALM)
    assert sessions.get_session(session_id).playing.track_id == tracks[1]
    with pytest.raises(InvalidSessionTransition):
        sessions.apply_turn(session_id, TurnKind.NEXT, occurrence_id=skipped.occurrence_id)


def test_next_with_nothing_queued_or_playing_is_still_recorded(sessions, listener):
    session_id = sessions.start_session(listener, _CALM).session.session_id

    turn = sessions.apply_turn(session_id, TurnKind.NEXT)

    assert (turn.kind, turn.occurrence_id) == (TurnKind.NEXT, None)


@pytest.mark.parametrize("kind", [TurnKind.NOT_FOR_ME, TurnKind.MORE_LIKE_THIS])
def test_turns_about_a_recommendation_default_to_the_playing_one(sessions, listener, tracks, kind):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    queue = _queue(sessions, session_id, tracks[:2]).queue
    playing = sessions.advance(session_id).playing

    about_playing = sessions.apply_turn(session_id, kind)
    about_queued = sessions.apply_turn(session_id, kind, occurrence_id=queue[1].occurrence_id)

    assert about_playing.occurrence_id == playing.occurrence_id
    assert about_queued.occurrence_id == queue[1].occurrence_id
    assert sessions.get_session(session_id).playing == playing  # B4 records the turn; its effect on ranking is B5/B6


def test_a_turn_about_a_recommendation_needs_one_from_this_session(sessions, listener, tracks, unit_of_work):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    with pytest.raises(InvalidSessionTransition):
        sessions.apply_turn(session_id, TurnKind.NOT_FOR_ME)  # nothing playing and none named

    other_listener = str(uuid.uuid4())
    with unit_of_work:
        unit_of_work.listener_profiles.add(ListenerProfile(other_listener, False, _NOW))
        unit_of_work.commit()
    other_session_id = sessions.start_session(other_listener, _CALM).session.session_id
    elsewhere = _queue(sessions, other_session_id, tracks[:1]).queue[0]

    with pytest.raises(RecommendationOccurrenceNotFound):
        sessions.apply_turn(session_id, TurnKind.NOT_FOR_ME, occurrence_id=elsewhere.occurrence_id)
    assert len(sessions.history(session_id).turns) == 1


@pytest.mark.parametrize("kind", [TurnKind.SURPRISE_ME, TurnKind.MORE_FAMILIAR, TurnKind.TRY_SOMETHING_DIFFERENT])
def test_exploration_turns_are_recorded_without_changing_state(sessions, listener, tracks, kind):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    _queue(sessions, session_id, tracks[:2])
    before = sessions.get_session(session_id)

    turn = sessions.apply_turn(session_id, kind)

    after = sessions.get_session(session_id)
    assert (turn.kind, turn.context, turn.occurrence_id) == (kind, _CALM, None)
    assert (after.playing, after.queue, after.session.current_context) == (before.playing, before.queue, before.session.current_context)


# --- History ---------------------------------------------------------------------------------


def test_history_includes_raw_feedback_events_in_order(sessions, listener, tracks, unit_of_work):
    session_id = sessions.start_session(listener, _CALM).session.session_id
    _queue(sessions, session_id, tracks[:1])
    playing = sessions.advance(session_id).playing
    events = [
        FeedbackEvent(str(uuid.uuid4()), session_id, playing.occurrence_id, FeedbackEventType.LIKE, _NOW + timedelta(minutes=1)),
        FeedbackEvent(str(uuid.uuid4()), session_id, playing.occurrence_id, FeedbackEventType.COMPLETE, _NOW + timedelta(minutes=4), 199.0, 200.0),
    ]
    with unit_of_work:  # recording events is B6; B4 stores and reads them
        for event in reversed(events):
            unit_of_work.feedback_events.add(event)
        unit_of_work.commit()

    assert sessions.history(session_id).feedback_events == tuple(events)
