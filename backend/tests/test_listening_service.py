"""ListeningService (B8, B9): session commands with the queue re-ranked after each, against a migrated SQLite database.

B9: every structured start and REFINE is checked against what the library can act on, before anything changes.
"""

import hashlib
import random
import uuid
from datetime import datetime, timezone

import pytest

from src.intentune.application.capability import IntentCapability
from src.intentune.application.listening import ListeningService
from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.intent import IntentUnavailable, LibraryNotReady
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
    return ListeningService(sessions, RecommendationService(unit_of_work, rng=_NeverExplore(0)), IntentCapability(unit_of_work))


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
    listening = ListeningService(sessions, FailingRecommendations(), IntentCapability(unit_of_work))

    with pytest.raises(RuntimeError):
        listening.steer(started.session.session_id, TurnKind.SURPRISE_ME)

    assert [turn.kind for turn in sessions.history(started.session.session_id).turns] == [TurnKind.INITIAL_INTENT, TurnKind.SURPRISE_ME]


# --- What the library can act on (B9) -----------------------------------------------------------
# The library here declares the genres ambient and jazz, no moods, and no energy (nothing measures it).


def _everything(sessions, session_id):
    """All a refused command must leave as it was: the context in force and the whole history (turns, queue, feedback)."""
    return sessions.get_session(session_id).session.current_context, sessions.history(session_id)


@pytest.mark.parametrize(
    "context, unavailable",
    [
        (ListeningContext(temporary_moods=("Calm",)), ("mood",)),
        (ListeningContext(desired_mood="Calm"), ("mood",)),
        (ListeningContext(target_energy=0.5), ("energy",)),
        (ListeningContext(temporary_genres=("polka",)), ("genre",)),
        (ListeningContext(temporary_moods=("Focused",), target_energy=0.5), ("mood", "energy")),
        (ListeningContext(temporary_genres=("ambient",), target_energy=0.3), ("energy",)),
        (ListeningContext(temporary_genres=("ambient",), target_valence=0.6, target_tempo_bpm=100), ("tempo", "valence")),
    ],
    ids=["mood", "desired-mood", "energy", "undeclared-genre", "the-focus-starter", "usable-genre-with-energy", "measured-targets"],
)
def test_a_start_asking_for_what_the_library_cannot_use_is_refused_before_anything_changes(listening, sessions, listener, ids, context, unavailable):
    playing_on = listening.start(listener, ListeningContext(temporary_genres=("jazz",))).session.session_id

    with pytest.raises(IntentUnavailable) as refused:
        listening.start(listener, context)

    assert (refused.value.unavailable, refused.value.supported) == (unavailable, ("genre",))
    # No misleading session was created, and the one in progress was not ended for it.
    assert [session.session_id for session in sessions.list_sessions(listener)] == [playing_on]
    assert sessions.get_session(playing_on).session.status is SessionStatus.ACTIVE


@pytest.mark.parametrize(
    "context, unavailable",
    [
        (ListeningContext(temporary_genres=("ambient",), temporary_moods=("Calm",)), ("mood",)),
        (ListeningContext(temporary_genres=("ambient",), desired_mood="Calm"), ("mood",)),
        (ListeningContext(temporary_genres=("ambient",), target_energy=0.7), ("energy",)),
        (ListeningContext(temporary_genres=("polka",)), ("genre",)),
        (ListeningContext(temporary_genres=("jazz",), target_energy=0.7), ("energy",)),
        (ListeningContext(temporary_genres=("ambient",), target_danceability=0.8), ("danceability",)),
    ],
    ids=["mood", "desired-mood", "energy", "undeclared-genre", "usable-genre-with-energy", "danceability"],
)
def test_a_refine_asking_for_what_the_library_cannot_use_is_refused_and_changes_nothing(listening, sessions, listener, ids, context, unavailable):
    """Not even the usable part of the refinement is applied: there is no partial success."""
    session_id = listening.start(listener, ListeningContext(temporary_genres=("ambient",))).session.session_id
    listening.next(session_id)
    before = _everything(sessions, session_id)

    with pytest.raises(IntentUnavailable) as refused:
        listening.steer(session_id, TurnKind.REFINE, context=context)

    assert refused.value.unavailable == unavailable
    assert _everything(sessions, session_id) == before  # no turn, no context change, no new queue


def test_what_the_library_can_use_is_applied_and_clearing_is_always_allowed(listening, sessions, listener, ids):
    """Only what a refinement changes is checked. A mood the library no longer declares (stored before it changed,
    as here, where the session is started past the check) neither blocks other changes nor can be kept from being cleared."""
    session_id = sessions.start_session(listener, ListeningContext(temporary_genres=("ambient",), temporary_moods=("Calm",))).session.session_id

    _, kept = listening.steer(session_id, TurnKind.REFINE, context=ListeningContext(temporary_genres=("jazz",), temporary_moods=("Calm",)))
    _, cleared = listening.steer(session_id, TurnKind.REFINE, context=ListeningContext(temporary_genres=("jazz",)))

    assert kept.session.current_context.temporary_moods == ("Calm",)
    assert sorted(_titles(kept.queue, ids)) == ["j1", "j2", "j3"]
    assert cleared.session.current_context == ListeningContext(temporary_genres=("jazz",))


def test_the_unmapped_context_fields_are_kept_and_stored_though_they_change_no_ranking(listening, listener, ids):
    stated = ListeningContext(temporary_genres=("ambient",), current_mood="tired", listening_goal="focus", activity="reading")

    state = listening.start(listener, stated)

    assert state.session.current_context == stated
    assert sorted(_titles(state.queue, ids)) == ["a1", "a2", "a3"]


# --- Before the library is ready (no ids: nothing is imported) --------------------------------------------


@pytest.mark.parametrize("context", [ListeningContext(), ListeningContext(temporary_genres=("ambient",), target_energy=0.5)], ids=["no-intent", "some-intent"])
def test_nothing_starts_before_the_library_has_playable_tracks(listening, sessions, listener, context):
    """A setup state, not unsupported dimensions: the answer is LibraryNotReady, whatever the intent."""
    with pytest.raises(LibraryNotReady):
        listening.start(listener, context)

    assert sessions.list_sessions(listener) == []


def test_a_refine_while_nothing_is_playable_is_refused_as_not_ready_and_changes_nothing(listening, sessions, listener):
    session_id = sessions.start_session(listener, ListeningContext()).session.session_id  # as before the tracks went missing
    before = _everything(sessions, session_id)

    with pytest.raises(LibraryNotReady):
        listening.steer(session_id, TurnKind.REFINE, context=ListeningContext(temporary_genres=("ambient",)))

    assert _everything(sessions, session_id) == before
