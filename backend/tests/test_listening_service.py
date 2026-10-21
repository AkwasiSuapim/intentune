"""ListeningService (B8): session commands with the queue re-ranked after each, against a migrated SQLite database."""

import hashlib
import random
import uuid
from datetime import datetime, timezone

import pytest

from src.intentune.application.listening import ListeningService
from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.session import InvalidSessionTransition, OccurrenceStatus, SessionStatus, TurnKind

_NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


class _NeverExplore(random.Random):
    def random(self):
        return 0.999


@pytest.fixture
def ids(unit_of_work):
    """Three ambient tracks (a*) and three jazz tracks (j*)."""
    titles = {}
    with unit_of_work:
        for title, genre in (("a1", "ambient"), ("a2", "ambient"), ("a3", "ambient"), ("j1", "jazz"), ("j2", "jazz"), ("j3", "jazz")):
            track = Track(
                track_id=str(uuid.uuid4()), sha256=hashlib.sha256(title.encode()).hexdigest(), size_bytes=10,
                audio_format=AudioFormat.FLAC, status=TrackStatus.READY, original_filename=f"{title}.flac",
                created_at=_NOW, updated_at=_NOW, title=title, artist=f"Artist {title}", analysis_version="test@1",
                labels=(TrackLabel(LabelKind.GENRE, genre, "tag", True),),
            )
            unit_of_work.tracks.add(track)
            titles[track.track_id] = title
        unit_of_work.commit()
    return titles


@pytest.fixture
def listener(unit_of_work):
    return ensure_default_listener(unit_of_work).listener_profile_id


@pytest.fixture
def sessions(unit_of_work):
    return SessionService(unit_of_work)


@pytest.fixture
def listening(unit_of_work, sessions):
    return ListeningService(sessions, RecommendationService(unit_of_work, rng=_NeverExplore(0)))


def _titles(occurrences, ids):
    return [ids[occurrence.track_id] for occurrence in occurrences]


def test_start_surfaces_the_first_queue_and_plays_nothing_yet(listening, sessions, listener, ids):
    state = listening.start(listener, ListeningContext(temporary_genres=("ambient",)))

    assert state.session.status is SessionStatus.ACTIVE
    assert state.playing is None
    assert sorted(_titles(state.queue, ids)) == ["a1", "a2", "a3"]
    history = sessions.history(state.session.session_id)
    assert [turn.kind for turn in history.turns] == [TurnKind.INITIAL_INTENT]


def test_start_ends_the_previous_session(listening, sessions, listener, ids):
    first = listening.start(listener, ListeningContext(temporary_genres=("ambient",)))
    listening.start(listener, ListeningContext(temporary_genres=("jazz",)))

    assert sessions.get_session(first.session.session_id).session.status is SessionStatus.ENDED


def test_next_while_nothing_plays_starts_the_first_queued_track_and_refills_the_queue(listening, sessions, listener, ids):
    started = listening.start(listener, ListeningContext(temporary_genres=("ambient",)))

    turn, state = listening.steer(started.session.session_id, TurnKind.NEXT)

    assert turn.kind is TurnKind.NEXT
    assert state.playing.track_id == started.queue[0].track_id
    assert state.playing.status is OccurrenceStatus.PLAYING
    assert state.playing.track_id not in {occurrence.track_id for occurrence in state.queue}
    assert state.queue  # re-ranked and refilled after the turn
    assert all(occurrence.surfaced_at > turn.created_at for occurrence in state.queue)


def test_refine_re_ranks_the_queue_for_the_new_context(listening, listener, ids):
    started = listening.start(listener, ListeningContext(temporary_genres=("ambient",)))

    _, state = listening.steer(started.session.session_id, TurnKind.REFINE, context=ListeningContext(temporary_genres=("jazz",)))

    assert state.session.current_context.temporary_genres == ("jazz",)
    assert sorted(_titles(state.queue, ids)) == ["j1", "j2", "j3"]


def test_a_refused_turn_changes_nothing(listening, sessions, listener, ids):
    started = listening.start(listener, ListeningContext(temporary_genres=("ambient",)))

    with pytest.raises(InvalidSessionTransition):
        listening.steer(started.session.session_id, TurnKind.INITIAL_INTENT)

    after = sessions.get_session(started.session.session_id)
    assert [occurrence.occurrence_id for occurrence in after.queue] == [occurrence.occurrence_id for occurrence in started.queue]
    assert len(sessions.history(started.session.session_id).turns) == 1


def test_a_failed_refresh_leaves_the_turn_recorded(unit_of_work, sessions, listener, ids):
    class FailingRecommendations:
        def refresh_queue(self, session_id):
            raise RuntimeError("policy failed")

    started = sessions.start_session(listener, ListeningContext(temporary_genres=("ambient",)))
    listening = ListeningService(sessions, FailingRecommendations())

    with pytest.raises(RuntimeError):
        listening.steer(started.session.session_id, TurnKind.SURPRISE_ME)

    assert [turn.kind for turn in sessions.history(started.session.session_id).turns] == [TurnKind.INITIAL_INTENT, TurnKind.SURPRISE_ME]
