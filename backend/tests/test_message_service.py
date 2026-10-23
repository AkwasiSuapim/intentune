"""MessageService (B9): typed words, interpreted in the backend, reach the same use cases as the controls.

Runs against a migrated SQLite database with the real deterministic interpreter.
"""

import hashlib
import random
import uuid
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.intentune.adapters.deterministic_intent import DeterministicIntentInterpreter
from src.intentune.application.adaptation import LongTermAdaptationService
from src.intentune.application.capability import IntentCapability
from src.intentune.application.feedback import FeedbackService
from src.intentune.application.listening import ListeningService, PlaybackFacts
from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.application.messages import MessageService
from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.intent import (
    IntentUnavailable,
    LibraryCapability,
    LibraryNotReady,
    MeaningKind,
    MessageNotUnderstood,
    NotUnderstoodReason,
    Vocabulary,
)
from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.session import FeedbackEventType, InvalidSessionTransition, OccurrenceStatus, SessionStatus, TurnKind

_NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


class _NeverExplore(random.Random):
    def random(self):
        return 0.999


@pytest.fixture
def ids(unit_of_work):
    """Three Ambient tracks (a*) and three Jazz ones (j*), as their tags declare them."""
    titles = {}
    with unit_of_work:
        for title, genre in (("a1", "Ambient"), ("a2", "Ambient"), ("a3", "Ambient"), ("j1", "Jazz"), ("j2", "Jazz"), ("j3", "Jazz")):
            track = Track(
                track_id=str(uuid.uuid4()), sha256=hashlib.sha256(title.encode()).hexdigest(), size_bytes=10,
                audio_format=AudioFormat.FLAC, status=TrackStatus.READY, original_filename=f"{title}.flac",
                created_at=_NOW, updated_at=_NOW, title=title, artist=f"Artist {title}", analysis_version="test@1",
                labels=(TrackLabel(LabelKind.GENRE, genre, "embedded_tags", True),),
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
def capability(unit_of_work):
    return IntentCapability(unit_of_work)


@pytest.fixture
def listening(unit_of_work, sessions, capability):
    return ListeningService(sessions, RecommendationService(unit_of_work, rng=_NeverExplore(0)), capability, LongTermAdaptationService(unit_of_work))


@pytest.fixture
def feedback(unit_of_work):
    return FeedbackService(unit_of_work, RecommendationService(unit_of_work, rng=_NeverExplore(0)), LongTermAdaptationService(unit_of_work))


@pytest.fixture
def messages(sessions, listening, feedback, capability):
    return MessageService(DeterministicIntentInterpreter(), sessions, listening, feedback, capability)


@pytest.fixture
def playing(listening, listener, ids):
    """An Ambient session with its first track playing: (session_id, state)."""
    session_id = listening.start(listener, ListeningContext(temporary_genres=("Ambient",))).session.session_id
    _, state = listening.next(session_id)
    assert state.playing is not None
    return session_id, state


def _titles(occurrences, ids):
    return [ids[occurrence.track_id] for occurrence in occurrences]


class _FixedCapability(IntentCapability):
    """The capability of a library with this vocabulary (which no library has today), counting the checks it is asked for."""

    def __init__(self, vocabulary):
        self.fixed = vocabulary
        self.checks = 0

    def vocabulary(self):
        return self.fixed

    def require(self, before, after, vocabulary=None):
        self.checks += 1
        super().require(before, after, vocabulary)


class _CountingRecommendations:
    """The real RecommendationService, counting how often the queue is re-ranked."""

    def __init__(self, inner):
        self._inner = inner
        self.refreshes = 0

    def refresh_queue(self, session_id):
        self.refreshes += 1
        return self._inner.refresh_queue(session_id)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _kinds(sessions, session_id):
    return [turn.kind for turn in sessions.history(session_id).turns]


def _events(sessions, session_id):
    return [event.event_type for event in sessions.history(session_id).feedback_events]


# --- Starting from words ------------------------------------------------------------------------


def test_words_that_refine_start_a_session_with_that_context(messages, sessions, listener, ids):
    outcome = messages.start(listener, "some jazz please")

    assert outcome.meaning.kind is MeaningKind.REFINE
    context = outcome.state.session.current_context
    assert (context.temporary_genres, context.target_energy) == (("Jazz",), None)
    assert sorted(_titles(outcome.state.queue, ids)) == ["j1", "j2", "j3"]
    assert _kinds(sessions, outcome.state.session.session_id) == [TurnKind.INITIAL_INTENT]


def test_a_session_control_starts_a_session_and_then_applies_it(messages, sessions, listener, ids):
    outcome = messages.start(listener, "surprise me")

    assert outcome.turn.kind is TurnKind.SURPRISE_ME
    assert outcome.state.session.current_context == ListeningContext()
    assert _kinds(sessions, outcome.state.session.session_id) == [TurnKind.INITIAL_INTENT, TurnKind.SURPRISE_ME]


@pytest.mark.parametrize(
    "text, reason",
    [
        ("like this", NotUnderstoodReason.NO_RECOMMENDATION),
        ("next", NotUnderstoodReason.NO_RECOMMENDATION),
        ("more like this", NotUnderstoodReason.NO_RECOMMENDATION),
        ("save this", NotUnderstoodReason.NO_RECOMMENDATION),
        ("music for driving through Accra at 2am", NotUnderstoodReason.UNRECOGNIZED),
        ("no jazz", NotUnderstoodReason.UNSUPPORTED),
    ],
)
def test_words_that_cannot_start_a_session_start_nothing(messages, sessions, listener, ids, text, reason):
    with pytest.raises(MessageNotUnderstood) as refused:
        messages.start(listener, text)

    assert refused.value.reason is reason
    assert sessions.list_sessions(listener) == []


# --- Words in a session -------------------------------------------------------------------------


def test_a_refinement_is_a_refine_turn_with_the_new_context(messages, sessions, ids, playing):
    session_id, state = playing

    outcome = messages.send(session_id, "more jazz please")

    assert outcome.turn.kind is TurnKind.REFINE
    assert outcome.state.session.current_context.temporary_genres == ("Jazz",)
    assert sorted(_titles(outcome.state.queue, ids)) == ["j1", "j2", "j3"]
    assert outcome.state.playing.occurrence_id == state.playing.occurrence_id  # music leads: the track plays on


@pytest.fixture
def energetic(unit_of_work, sessions, feedback):
    """Listening and messages over a library that, unlike any today, has energy and mood evidence."""
    capability = _FixedCapability(
        Vocabulary(genres=("Ambient", "Jazz"), library_moods=("Calm",), capability=LibraryCapability(6, ("mood", "genre", "energy")))
    )
    listening = ListeningService(sessions, RecommendationService(unit_of_work, rng=_NeverExplore(0)), capability, LongTermAdaptationService(unit_of_work))
    return listening, MessageService(DeterministicIntentInterpreter(), sessions, listening, feedback, capability)


def test_relative_words_read_the_context_in_force(energetic, listener, ids):
    listening, messages = energetic
    session_id = listening.start(listener, ListeningContext(target_energy=0.7)).session.session_id

    assert messages.send(session_id, "calmer").state.session.current_context.target_energy == 0.5
    assert messages.send(session_id, "something calm").state.session.current_context.temporary_moods == ("Calm",)


def test_energy_the_library_cannot_use_is_understood_and_refused_not_pretended(messages, sessions, listening, listener, ids):
    """No track has an energy value, so asking for more or less energy would change nothing that plays."""
    session_id = listening.start(listener, ListeningContext(temporary_genres=("Ambient",))).session.session_id
    before = sessions.history(session_id)

    with pytest.raises(IntentUnavailable) as refused:
        messages.send(session_id, "a bit calmer")

    assert (refused.value.unavailable, refused.value.supported) == (("energy",), ("genre",))
    assert sessions.history(session_id) == before
    with pytest.raises(IntentUnavailable) as at_start:
        messages.start(listener, "jazz, more energetic")
    assert at_start.value.unavailable == ("energy",)
    assert [session.session_id for session in sessions.list_sessions(listener)] == [session_id]  # nothing started


def test_a_mood_no_track_declares_is_refused_and_clearing_one_is_always_allowed(messages, listening, listener, ids):
    session_id = listening.start(listener, ListeningContext()).session.session_id

    with pytest.raises(IntentUnavailable) as refused:
        messages.send(session_id, "something focused")

    assert refused.value.unavailable == ("mood",)
    assert messages.send(session_id, "any genre").meaning.kind is MeaningKind.REFINE


def test_typed_and_structured_intent_meet_the_same_capability_rule(unit_of_work, sessions, feedback, listener, ids):
    """One capability answers both paths: what it refuses, both refuse alike, and what it allows, both apply."""
    capability = _FixedCapability(Vocabulary(genres=("Ambient", "Jazz"), capability=LibraryCapability(6, ("genre",))))
    listening = ListeningService(sessions, RecommendationService(unit_of_work, rng=_NeverExplore(0)), capability, LongTermAdaptationService(unit_of_work))
    messages = MessageService(DeterministicIntentInterpreter(), sessions, listening, feedback, capability)
    session_id = listening.start(listener, ListeningContext(temporary_genres=("Ambient",))).session.session_id
    capability.checks = 0

    with pytest.raises(IntentUnavailable) as typed:
        messages.send(session_id, "more energy")
    with pytest.raises(IntentUnavailable) as structured:
        listening.steer(session_id, TurnKind.REFINE, context=ListeningContext(temporary_genres=("Ambient",), target_energy=0.7))

    assert (typed.value.unavailable, typed.value.supported) == (structured.value.unavailable, structured.value.supported)
    assert (typed.value.unavailable, typed.value.supported) == (("energy",), ("genre",))
    assert capability.checks == 2  # each path asked the capability once

    capability.fixed = replace(capability.fixed, capability=LibraryCapability(6, ("genre", "energy")))  # the library gains energy
    assert messages.send(session_id, "more energy").state.session.current_context.target_energy == 0.7
    _, state = listening.steer(session_id, TurnKind.REFINE, context=ListeningContext(temporary_genres=("Ambient",), target_energy=0.9))
    assert state.session.current_context.target_energy == 0.9


def test_refusals_name_only_the_dimensions_the_library_can_use(messages, listener, ids):
    with pytest.raises(MessageNotUnderstood) as refused:
        messages.start(listener, "music for a rainy night drive")

    assert refused.value.supported == ("genre",)


@pytest.mark.parametrize("text, kind", [("surprise me", TurnKind.SURPRISE_ME), ("more familiar", TurnKind.MORE_FAMILIAR), ("try something different", TurnKind.TRY_SOMETHING_DIFFERENT)])
def test_session_controls_are_turns_without_a_target(messages, sessions, playing, text, kind):
    session_id, _ = playing

    outcome = messages.send(session_id, text)

    assert (outcome.turn.kind, outcome.turn.occurrence_id) == (kind, None)


def test_more_like_this_and_not_for_me_are_about_the_recommendation_in_view(messages, sessions, ids, playing):
    session_id, state = playing
    upcoming = state.queue[0]

    liked_direction = messages.send(session_id, "more like this", occurrence_id=upcoming.occurrence_id)
    refused = messages.send(session_id, "not for me")  # without one in view: the playing track

    assert (liked_direction.turn.kind, liked_direction.turn.occurrence_id) == (TurnKind.MORE_LIKE_THIS, upcoming.occurrence_id)
    assert (refused.turn.kind, refused.turn.occurrence_id) == (TurnKind.NOT_FOR_ME, state.playing.occurrence_id)
    assert refused.state.playing.track_id != state.playing.track_id  # a rejected track does not keep playing


def test_typed_next_records_what_the_clicked_next_records(messages, listening, sessions, listener, ids):
    """The typed and clicked paths converge on ListeningService.next(): the NEXT turn, then the SKIP fact."""
    histories = []
    for typed in (True, False):
        session_id = listening.start(listener, ListeningContext(temporary_genres=("Ambient",))).session.session_id
        _, state = listening.next(session_id)
        facts = PlaybackFacts(played_seconds=12.0, duration_seconds=200.0)
        if typed:
            outcome = messages.send(session_id, "skip this", occurrence_id=state.playing.occurrence_id, playback=facts)
            assert outcome.meaning.turn is TurnKind.NEXT
        else:
            listening.next(session_id, occurrence_id=state.playing.occurrence_id, playback=facts)
        history = sessions.history(session_id)
        [skip] = history.feedback_events
        histories.append((
            [turn.kind for turn in history.turns],
            (skip.event_type, skip.occurrence_id == state.playing.occurrence_id, skip.played_seconds, skip.duration_seconds),
        ))

    assert histories[0] == histories[1]
    assert histories[0] == ([TurnKind.INITIAL_INTENT, TurnKind.NEXT, TurnKind.NEXT], (FeedbackEventType.SKIP, True, 12.0, 200.0))


def test_typed_reactions_record_the_same_feedback_as_the_buttons(messages, sessions, playing):
    session_id, state = playing

    liked = messages.send(session_id, "I like this")
    replayed = messages.send(session_id, "play that again")

    assert (liked.feedback.event.event_type, liked.feedback.event_weight) == (FeedbackEventType.LIKE, 1.0)
    assert liked.feedback.event.occurrence_id == state.playing.occurrence_id
    assert replayed.feedback.event.event_type is FeedbackEventType.REPLAY
    assert _events(sessions, session_id) == [FeedbackEventType.LIKE, FeedbackEventType.REPLAY]


def test_a_typed_reaction_is_about_the_recommendation_in_view(messages, sessions, playing):
    """"Like this" means the card the listener is looking at, which the UI names; it need not be the one playing."""
    session_id, state = playing
    upcoming = state.queue[0]

    outcome = messages.send(session_id, "like this", occurrence_id=upcoming.occurrence_id)

    assert outcome.feedback.event.occurrence_id == upcoming.occurrence_id
    assert outcome.feedback.event.occurrence_id != state.playing.occurrence_id


def test_save_this_asks_where_and_adds_nothing(messages, sessions, playing):
    session_id, state = playing
    before = sessions.history(session_id)

    outcome = messages.send(session_id, "save this")

    assert outcome.meaning.kind is MeaningKind.SAVE_REQUESTED
    assert (outcome.turn, outcome.feedback) == (None, None)
    assert outcome.state.playing.occurrence_id == state.playing.occurrence_id
    assert sessions.history(session_id) == before  # nothing recorded


@pytest.mark.parametrize("text", ["what a day", "skip this and save it", "not jazz"])
def test_words_that_cannot_be_acted_on_change_and_record_nothing(messages, sessions, playing, text):
    session_id, _ = playing
    before = sessions.history(session_id)

    with pytest.raises(MessageNotUnderstood):
        messages.send(session_id, text)

    assert sessions.history(session_id) == before


def test_words_about_a_recommendation_need_one(messages, listening, sessions, listener, ids):
    """Before anything plays, there is no recommendation to like."""
    session_id = listening.start(listener, ListeningContext()).session.session_id

    with pytest.raises(MessageNotUnderstood) as refused:
        messages.send(session_id, "like this")

    assert refused.value.reason is NotUnderstoodReason.NO_RECOMMENDATION


def test_words_in_an_ended_session_are_refused_as_any_command_is(messages, listening, sessions, listener, ids, playing):
    session_id, _ = playing
    listening.start(listener, ListeningContext())
    assert sessions.get_session(session_id).session.status is SessionStatus.ENDED

    with pytest.raises(InvalidSessionTransition):
        messages.send(session_id, "more jazz")


def test_the_typed_text_is_never_stored(messages, sessions, engine, playing):
    session_id, _ = playing
    messages.send(session_id, "more jazz, zebra-unique-phrase")

    with engine.connect() as connection:
        tables = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'").scalars().all()
        for table in tables:
            for row in connection.exec_driver_sql(f'SELECT * FROM "{table}"').all():
                assert not any("zebra" in str(value) for value in row), table


# --- ListeningService.next ------------------------------------------------------------------------


@pytest.mark.parametrize("typed", [False, True], ids=["clicked", "typed"])
def test_one_next_with_the_players_facts_re_ranks_exactly_once(unit_of_work, sessions, listener, ids, media_root, typed):
    """The SKIP is a late report about the track Next ended: it is kept as a raw event, and it does not re-rank again.

    One counter serves the listening and the feedback services alike, so a second
    refresh from either path would be counted.
    """
    recommendations = _CountingRecommendations(RecommendationService(unit_of_work, rng=_NeverExplore(0)))
    capability = IntentCapability(unit_of_work)
    listening = ListeningService(sessions, recommendations, capability, LongTermAdaptationService(unit_of_work))
    feedback = FeedbackService(unit_of_work, recommendations, LongTermAdaptationService(unit_of_work))
    messages = MessageService(DeterministicIntentInterpreter(), sessions, listening, feedback, capability)
    session_id = listening.start(listener, ListeningContext(temporary_genres=("Ambient",))).session.session_id
    _, state = listening.next(session_id)
    recommendations.refreshes = 0
    surfaced_before = {occurrence.occurrence_id for occurrence in sessions.history(session_id).occurrences}

    facts = PlaybackFacts(played_seconds=30.0, duration_seconds=200.0)
    if typed:
        after = messages.send(session_id, "next", occurrence_id=state.playing.occurrence_id, playback=facts).state
    else:
        _, after = listening.next(session_id, occurrence_id=state.playing.occurrence_id, playback=facts)

    assert recommendations.refreshes == 1
    history = sessions.history(session_id)
    [skip] = history.feedback_events
    assert (skip.event_type, skip.occurrence_id) == (FeedbackEventType.SKIP, state.playing.occurrence_id)
    # The occurrences surfaced by this Next are exactly the one new queue: none was surfaced and then replaced.
    surfaced_now = {occurrence.occurrence_id for occurrence in history.occurrences} - surfaced_before
    assert after.queue and surfaced_now == {occurrence.occurrence_id for occurrence in after.queue}


def test_next_while_nothing_plays_starts_listening_and_records_no_skip(listening, sessions, listener, ids):
    started = listening.start(listener, ListeningContext(temporary_genres=("Ambient",)))

    turn, state = listening.next(started.session.session_id, playback=PlaybackFacts(30.0, 200.0))

    assert turn.occurrence_id is None
    assert state.playing.occurrence_id == started.queue[0].occurrence_id
    assert _events(sessions, started.session.session_id) == []  # nothing had played, so nothing was skipped


def test_next_records_the_skip_about_the_track_it_ended_and_moves_once(listening, sessions, ids, playing):
    session_id, state = playing

    turn, after = listening.next(session_id, playback=PlaybackFacts(30.0, 200.0))

    [skip] = sessions.history(session_id).feedback_events
    assert (turn.occurrence_id, skip.occurrence_id) == (state.playing.occurrence_id, state.playing.occurrence_id)
    assert (skip.event_type, skip.played_fraction) == (FeedbackEventType.SKIP, 0.15)
    assert after.playing.occurrence_id == state.queue[0].occurrence_id  # one track on, not two
    finished = [occurrence for occurrence in sessions.history(session_id).occurrences if occurrence.occurrence_id == state.playing.occurrence_id]
    assert finished[0].status is OccurrenceStatus.PLAYED


# --- Before the library is ready -------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["surprise me", "some jazz please", "a bit calmer", "music for a rainy night", "like this"])
def test_nothing_starts_from_words_before_the_library_has_playable_music(messages, sessions, listener, text):
    """Whatever the words, the answer is that the library is not ready: not that they were misunderstood or unsupported."""
    with pytest.raises(LibraryNotReady):
        messages.start(listener, text)

    assert sessions.list_sessions(listener) == []
