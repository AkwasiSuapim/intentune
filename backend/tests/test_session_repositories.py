"""SQLite session repositories against a migrated database: round trips, the context codec, and database rules."""

import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.domain.library import AudioFormat, Track, TrackStatus
from src.intentune.domain.listener import ListenerProfile
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.session import (
    FeedbackEvent,
    FeedbackEventType,
    OccurrenceStatus,
    RecommendationOccurrence,
    SessionEndReason,
    TurnKind,
    new_session,
    new_turn,
)
from src.intentune.persistence.repositories import context_from_json, context_to_json

_NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
_FULL_CONTEXT = ListeningContext(
    current_mood="tired",
    desired_mood="calm",
    listening_goal="focus",
    activity="reading",
    temporary_genres=("ambient", "jazz"),
    temporary_moods=("calm",),
    target_energy=0.25,
    target_danceability=0.1,
    target_tempo_bpm=80,
    target_valence=0.6,
    target_acousticness=0.9,
)


def _listener(unit_of_work):
    return ensure_default_listener(unit_of_work).listener_profile_id


def _track(unit_of_work, sha_char="a"):
    track = Track(
        track_id=str(uuid.uuid4()),
        sha256=sha_char * 64,
        size_bytes=10,
        audio_format=AudioFormat.FLAC,
        status=TrackStatus.IMPORTED,
        original_filename="song.flac",
        created_at=_NOW,
        updated_at=_NOW,
    )
    with unit_of_work:
        unit_of_work.tracks.add(track)
        unit_of_work.commit()
    return track


def _start(unit_of_work, listener_id, context=_FULL_CONTEXT, started_at=_NOW):
    session = new_session(listener_id, context, started_at)
    with unit_of_work:
        unit_of_work.listening_sessions.add(session)
        unit_of_work.session_turns.add(new_turn(session, 1, TurnKind.INITIAL_INTENT, context, started_at))
        unit_of_work.commit()
    return session


def _queued(session, track, position=0, rank=1):
    return RecommendationOccurrence(
        occurrence_id=str(uuid.uuid4()),
        session_id=session.session_id,
        track_id=track.track_id,
        rank=rank,
        algorithm="test-algorithm-v1",
        status=OccurrenceStatus.QUEUED,
        surfaced_at=_NOW,
        updated_at=_NOW,
        surfaced_position=position,
        score=0.75,
        queue_position=position,
    )


def _add_occurrences(unit_of_work, *occurrences):
    with unit_of_work:
        for occurrence in occurrences:
            unit_of_work.recommendation_occurrences.add(occurrence)
        unit_of_work.commit()


# --- Context codec ---------------------------------------------------------------------


@pytest.mark.parametrize("context", [_FULL_CONTEXT, ListeningContext()])
def test_context_json_round_trips_every_field(context):
    assert context_from_json(context_to_json(context)) == context


def test_context_json_is_compact_sorted_and_versioned():
    payload = json.loads(context_to_json(ListeningContext(target_energy=0.5)))

    assert payload["format"] == 1
    assert list(payload["context"]) == sorted(payload["context"])
    assert payload["context"]["target_energy"] == 0.5
    assert payload["context"]["temporary_genres"] == []


@pytest.mark.parametrize(
    "stored",
    [
        '{"format": 2, "context": {}}',
        '{"context": {}}',
        '{"format": 1, "context": {"target_energy": 0.5, "prompt": "something calm"}}',
        '{"format": 1, "context": {"target_energy": 7}}',
        "[]",
    ],
)
def test_unexpected_stored_context_is_refused_not_ignored(stored):
    with pytest.raises(ValueError):
        context_from_json(stored)


# --- Sessions and turns ------------------------------------------------------------------


def test_session_round_trip_and_save(unit_of_work):
    session = _start(unit_of_work, _listener(unit_of_work))
    ended = session.ended(SessionEndReason.ENDED_BY_LISTENER, _NOW + timedelta(hours=1))

    with unit_of_work:
        assert unit_of_work.listening_sessions.get(session.session_id) == session
        assert unit_of_work.listening_sessions.get_active_for_listener(session.listener_profile_id) == session
        unit_of_work.listening_sessions.save(ended)
        unit_of_work.commit()

    with unit_of_work:
        assert unit_of_work.listening_sessions.get(session.session_id) == ended
        assert unit_of_work.listening_sessions.get_active_for_listener(session.listener_profile_id) is None
        assert unit_of_work.listening_sessions.list_active() == []


def test_sessions_are_listed_newest_first(unit_of_work):
    listener = _listener(unit_of_work)
    older = _start(unit_of_work, listener)
    with unit_of_work:
        unit_of_work.listening_sessions.save(older.ended(SessionEndReason.ENDED_BY_LISTENER, _NOW))
        unit_of_work.commit()
    newer = _start(unit_of_work, listener, started_at=_NOW + timedelta(days=1))

    with unit_of_work:
        assert [session.session_id for session in unit_of_work.listening_sessions.list_for_listener(listener)] == [
            newer.session_id,
            older.session_id,
        ]


def test_turns_round_trip_in_sequence(unit_of_work):
    session = _start(unit_of_work, _listener(unit_of_work))
    refined = ListeningContext(target_energy=0.9)
    with unit_of_work:
        unit_of_work.session_turns.add(new_turn(session, 2, TurnKind.REFINE, refined, _NOW + timedelta(seconds=5)))
        unit_of_work.commit()

    with unit_of_work:
        turns = unit_of_work.session_turns.list_for_session(session.session_id)

    assert [(turn.sequence, turn.kind, turn.context) for turn in turns] == [
        (1, TurnKind.INITIAL_INTENT, _FULL_CONTEXT),
        (2, TurnKind.REFINE, refined),
    ]


def test_turn_sequences_are_unique_per_session(unit_of_work):
    session = _start(unit_of_work, _listener(unit_of_work))

    with pytest.raises(IntegrityError):
        with unit_of_work:
            unit_of_work.session_turns.add(new_turn(session, 1, TurnKind.INITIAL_INTENT, _FULL_CONTEXT, _NOW))


def test_a_listener_has_at_most_one_active_session(unit_of_work):
    listener = _listener(unit_of_work)
    _start(unit_of_work, listener)

    with pytest.raises(IntegrityError):
        _start(unit_of_work, listener)


# --- Occurrences --------------------------------------------------------------------------


def test_occurrences_round_trip_and_the_queue_is_in_position_order(unit_of_work):
    session = _start(unit_of_work, _listener(unit_of_work))
    first, second, third = (_track(unit_of_work, char) for char in "abc")
    later_rank_first = _queued(session, second, position=0, rank=2)
    earlier_rank_second = _queued(session, first, position=1, rank=1)
    _add_occurrences(unit_of_work, earlier_rank_second, later_rank_first, _queued(session, third, position=2, rank=3))

    with unit_of_work:
        queue = unit_of_work.recommendation_occurrences.list_for_session(session.session_id, OccurrenceStatus.QUEUED)
        loaded = unit_of_work.recommendation_occurrences.get(later_rank_first.occurrence_id)

    assert [occurrence.track_id for occurrence in queue] == [second.track_id, first.track_id, third.track_id]
    assert loaded == later_rank_first


def test_the_surfaced_order_is_kept_after_the_queue_moves_on(unit_of_work):
    """Rank 2 surfaced ahead of rank 1 can still be read back once neither is QUEUED (B5)."""
    session = _start(unit_of_work, _listener(unit_of_work))
    first, second, third = (_track(unit_of_work, char) for char in "abc")
    second_first = [_queued(session, second, position=0, rank=2), _queued(session, first, position=1, rank=1), _queued(session, third, position=2, rank=3)]
    _add_occurrences(unit_of_work, *second_first)
    with unit_of_work:
        unit_of_work.recommendation_occurrences.save(second_first[0].started_playing(_NOW).finished_playing(_NOW + timedelta(seconds=5)))
        for still_queued in second_first[1:]:
            unit_of_work.recommendation_occurrences.save(still_queued.replaced(_NOW + timedelta(seconds=5)))
        unit_of_work.commit()

    with unit_of_work:
        history = unit_of_work.recommendation_occurrences.list_for_session(session.session_id)

    assert [occurrence.queue_position for occurrence in history] == [None, None, None]
    assert [(occurrence.surfaced_position, occurrence.rank) for occurrence in history] == [(0, 2), (1, 1), (2, 3)]


def test_saving_never_rewrites_what_was_surfaced(unit_of_work):
    session = _start(unit_of_work, _listener(unit_of_work))
    occurrence = _queued(session, _track(unit_of_work), position=1, rank=2)
    _add_occurrences(unit_of_work, occurrence)
    rewritten = replace(occurrence.started_playing(_NOW), surfaced_position=0, rank=1, score=0.1, is_exploration=True)

    with unit_of_work:
        unit_of_work.recommendation_occurrences.save(rewritten)
        unit_of_work.commit()

    with unit_of_work:
        stored = unit_of_work.recommendation_occurrences.get(occurrence.occurrence_id)
    assert stored.status is OccurrenceStatus.PLAYING
    assert (stored.surfaced_position, stored.rank, stored.score, stored.is_exploration) == (1, 2, 0.75, False)


@pytest.mark.parametrize("column, value", [("surfaced_position", -1), ("surfaced_position", None), ("is_exploration", 2)])
def test_database_refuses_surfacing_values_the_domain_would_not_create(engine, unit_of_work, column, value):
    session = _start(unit_of_work, _listener(unit_of_work))
    _add_occurrences(unit_of_work, _queued(session, _track(unit_of_work)))

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(f"UPDATE recommendation_occurrences SET {column} = ?", (value,))


def test_occurrence_save_and_status_filter(unit_of_work):
    session = _start(unit_of_work, _listener(unit_of_work))
    occurrence = _queued(session, _track(unit_of_work))
    _add_occurrences(unit_of_work, occurrence)
    playing = occurrence.started_playing(_NOW + timedelta(seconds=1))

    with unit_of_work:
        unit_of_work.recommendation_occurrences.save(playing)
        unit_of_work.commit()

    with unit_of_work:
        assert unit_of_work.recommendation_occurrences.list_for_session(session.session_id, OccurrenceStatus.PLAYING) == [playing]
        assert unit_of_work.recommendation_occurrences.list_for_session(session.session_id, OccurrenceStatus.QUEUED) == []


def test_a_session_has_at_most_one_playing_occurrence(unit_of_work):
    session = _start(unit_of_work, _listener(unit_of_work))
    first, second = _queued(session, _track(unit_of_work, "a"), 0), _queued(session, _track(unit_of_work, "b"), 1)
    _add_occurrences(unit_of_work, first, second)
    with unit_of_work:
        unit_of_work.recommendation_occurrences.save(first.started_playing(_NOW))
        unit_of_work.commit()

    with pytest.raises(IntegrityError):
        with unit_of_work:
            unit_of_work.recommendation_occurrences.save(second.started_playing(_NOW))


def test_queue_positions_are_unique_per_session(unit_of_work):
    session = _start(unit_of_work, _listener(unit_of_work))

    with pytest.raises(IntegrityError):
        _add_occurrences(unit_of_work, _queued(session, _track(unit_of_work, "a"), 0), _queued(session, _track(unit_of_work, "b"), 0))


def test_occurrences_must_reference_an_existing_track(unit_of_work):
    session = _start(unit_of_work, _listener(unit_of_work))
    ghost = Track(
        track_id=str(uuid.uuid4()), sha256="f" * 64, size_bytes=1, audio_format="mp3", status="IMPORTED",
        original_filename="x.mp3", created_at=_NOW, updated_at=_NOW,
    )

    with pytest.raises(IntegrityError):
        _add_occurrences(unit_of_work, _queued(session, ghost))


# --- Feedback events ------------------------------------------------------------------------


def test_feedback_events_round_trip_with_the_derived_fraction_stored(unit_of_work, engine):
    session = _start(unit_of_work, _listener(unit_of_work))
    occurrence = _queued(session, _track(unit_of_work))
    _add_occurrences(unit_of_work, occurrence)
    skip = FeedbackEvent(str(uuid.uuid4()), session.session_id, occurrence.occurrence_id, FeedbackEventType.SKIP, _NOW, 30, 120)
    like = FeedbackEvent(str(uuid.uuid4()), session.session_id, occurrence.occurrence_id, FeedbackEventType.LIKE, _NOW + timedelta(seconds=1))

    with unit_of_work:
        unit_of_work.feedback_events.add(like)
        unit_of_work.feedback_events.add(skip)
        unit_of_work.commit()

    with unit_of_work:
        assert unit_of_work.feedback_events.list_for_session(session.session_id) == [skip, like]
    with engine.connect() as connection:
        stored = connection.exec_driver_sql("SELECT played_fraction FROM feedback_events WHERE event_type = 'SKIP'").scalar_one()
    assert stored == pytest.approx(0.25)


def _second_session_with_occurrence(unit_of_work):
    """Two sessions of different listeners, each with an occurrence."""
    first = _start(unit_of_work, _listener(unit_of_work))
    other_listener = str(uuid.uuid4())
    with unit_of_work:
        unit_of_work.listener_profiles.add(ListenerProfile(other_listener, False, _NOW))
        unit_of_work.commit()
    second = _start(unit_of_work, other_listener)
    elsewhere = _queued(second, _track(unit_of_work))
    _add_occurrences(unit_of_work, elsewhere)
    return first, elsewhere


def test_a_feedback_event_cannot_point_at_another_sessions_occurrence(unit_of_work):
    first, elsewhere = _second_session_with_occurrence(unit_of_work)

    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with unit_of_work:
            unit_of_work.feedback_events.add(
                FeedbackEvent(str(uuid.uuid4()), first.session_id, elsewhere.occurrence_id, FeedbackEventType.LIKE, _NOW)
            )


def test_a_turn_cannot_point_at_another_sessions_occurrence(unit_of_work):
    first, elsewhere = _second_session_with_occurrence(unit_of_work)

    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with unit_of_work:
            unit_of_work.session_turns.add(
                new_turn(first, 2, TurnKind.NOT_FOR_ME, _FULL_CONTEXT, _NOW, occurrence_id=elsewhere.occurrence_id)
            )


@pytest.mark.parametrize(
    "event_type, played, duration, fraction",
    [("SKIP", None, None, None), ("LIKE", 10.0, None, None), ("LIKE", 10.0, 100.0, None), ("PROGRESS", None, None, None), ("COMPLETE", 10.0, 0.0, 1.0)],
)
def test_database_refuses_feedback_rows_the_domain_would_not_create(engine, unit_of_work, event_type, played, duration, fraction):
    session = _start(unit_of_work, _listener(unit_of_work))
    occurrence = _queued(session, _track(unit_of_work))
    _add_occurrences(unit_of_work, occurrence)

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO feedback_events (id, session_id, occurrence_id, event_type, played_seconds, duration_seconds, played_fraction, occurred_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, '2026-10-20 09:00:00')",
                (str(uuid.uuid4()), session.session_id, occurrence.occurrence_id, event_type, played, duration, fraction),
            )


# --- What is never stored -------------------------------------------------------------------


# --- A listener's whole history in one read (B11) ----------------------------------------------------


def test_a_listeners_history_reads_as_its_sessions_would_one_by_one_and_nothing_of_anyone_else(unit_of_work):
    listener = _listener(unit_of_work)
    older = _start(unit_of_work, listener)
    track, other_track = _track(unit_of_work, "a"), _track(unit_of_work, "b")
    first, second = _queued(older, track, position=0), _queued(older, other_track, position=1, rank=2)
    _add_occurrences(unit_of_work, second, first)
    with unit_of_work:
        unit_of_work.session_turns.add(new_turn(older, 2, TurnKind.NOT_FOR_ME, _FULL_CONTEXT, _NOW, first.occurrence_id))
        unit_of_work.feedback_events.add(
            FeedbackEvent(str(uuid.uuid4()), older.session_id, second.occurrence_id, FeedbackEventType.LIKE, _NOW + timedelta(seconds=2))
        )
        unit_of_work.feedback_events.add(
            FeedbackEvent(str(uuid.uuid4()), older.session_id, first.occurrence_id, FeedbackEventType.SKIP, _NOW + timedelta(seconds=1), 30, 120)
        )
        unit_of_work.listening_sessions.save(older.ended(SessionEndReason.ENDED_BY_LISTENER, _NOW + timedelta(hours=1)))
        unit_of_work.commit()
    newer = _start(unit_of_work, listener, started_at=_NOW + timedelta(days=1))
    _add_occurrences(unit_of_work, _queued(newer, track))
    _, elsewhere = _second_session_with_occurrence_of_another_listener(unit_of_work)

    with unit_of_work:
        sessions = [older.session_id, newer.session_id]
        one_by_one = (
            [turn for session_id in sessions for turn in unit_of_work.session_turns.list_for_session(session_id)],
            [item for session_id in sessions for item in unit_of_work.recommendation_occurrences.list_for_session(session_id)],
            [event for session_id in sessions for event in unit_of_work.feedback_events.list_for_session(session_id)],
        )
        at_once = (
            unit_of_work.session_turns.list_for_listener(listener),
            unit_of_work.recommendation_occurrences.list_for_listener(listener),
            unit_of_work.feedback_events.list_for_listener(listener),
        )

    def by_session(items):
        return {session_id: [item for item in items if item.session_id == session_id] for session_id in sessions}

    assert [by_session(listed) for listed in at_once] == [by_session(expected) for expected in one_by_one]
    assert [len(listed) for listed in at_once] == [len(expected) for expected in one_by_one] == [3, 3, 2]
    assert elsewhere.occurrence_id not in {item.occurrence_id for item in at_once[1]}


def _second_session_with_occurrence_of_another_listener(unit_of_work):
    other_listener = str(uuid.uuid4())
    with unit_of_work:
        unit_of_work.listener_profiles.add(ListenerProfile(other_listener, False, _NOW))
        unit_of_work.commit()
    session = _start(unit_of_work, other_listener)
    occurrence = _queued(session, _track(unit_of_work, "c"))
    _add_occurrences(unit_of_work, occurrence)
    return session, occurrence


def test_session_tables_have_no_column_for_raw_text_or_ui_state(engine):
    """D33: no raw conversational text. D32: no UI-only state. Context is stored as structured JSON only."""
    inspector = inspect(engine)
    columns = {table: {column["name"] for column in inspector.get_columns(table)} for table in (
        "listening_sessions", "session_turns", "recommendation_occurrences", "feedback_events"
    )}

    assert columns["listening_sessions"] == {"id", "listener_profile_id", "status", "end_reason", "context_json", "started_at", "updated_at", "ended_at"}
    assert columns["session_turns"] == {"id", "session_id", "sequence", "kind", "context_json", "occurrence_id", "created_at"}
    assert columns["feedback_events"] == {
        "id", "session_id", "occurrence_id", "event_type", "played_seconds", "duration_seconds", "played_fraction", "occurred_at"
    }
    assert columns["recommendation_occurrences"] == {
        "id", "session_id", "track_id", "rank", "score", "algorithm", "status", "queue_position", "surfaced_at", "updated_at",
        "started_at", "finished_at", "surfaced_position", "is_exploration",  # the last two: added in B5
    }
