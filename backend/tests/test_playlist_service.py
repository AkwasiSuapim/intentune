"""PlaylistService application tests against a migrated SQLite database (Prototype 1, phase B7).

Execution guide §10:
- create, rename, delete, add, remove, and reorder;
- one entry per track per playlist;
- a playlist add is strong positive feedback, but nothing is ever saved automatically.

A track added from a recommendation in a session is recorded as PLAYLIST_ADD
feedback and re-ranks the queue. An add that is refused stores neither an item
nor an event.
"""

import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.intentune.application.adaptation import LongTermAdaptationService
from src.intentune.application.feedback import FeedbackService
from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.application.playlists import PlaylistService
from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackNotFound, TrackStatus
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.playlist import InvalidPlaylistOrder, PlaylistNameTaken, PlaylistNotFound, TrackAlreadyInPlaylist, TrackNotInPlaylist
from src.intentune.domain.policy import EvidenceBasis
from src.intentune.domain.session import (
    FeedbackEventType,
    InvalidSessionTransition,
    ListenerProfileNotFound,
    RecommendationOccurrenceNotFound,
)
from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork

_NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
_AMBIENT = ListeningContext(temporary_genres=("ambient",))


class SteppingClock:
    def __init__(self):
        self._now = _NOW

    def __call__(self):
        self._now += timedelta(seconds=1)
        return self._now


class _NeverExplore(random.Random):
    def random(self):
        return 0.999


@pytest.fixture
def clock():
    return SteppingClock()


@pytest.fixture
def sessions(unit_of_work, clock):
    return SessionService(unit_of_work, clock=clock)


@pytest.fixture
def recommender(unit_of_work, clock):
    return RecommendationService(unit_of_work, rng=_NeverExplore(0), clock=clock)


@pytest.fixture
def feedback(unit_of_work, recommender, clock):
    return FeedbackService(unit_of_work, recommender, LongTermAdaptationService(unit_of_work, clock=clock), clock=clock)


@pytest.fixture
def playlists(unit_of_work, feedback, clock):
    return PlaylistService(unit_of_work, feedback, clock=clock)


@pytest.fixture
def listener(unit_of_work):
    return ensure_default_listener(unit_of_work).listener_profile_id


@pytest.fixture
def ids(unit_of_work):
    """Ambient tracks: three dark ones (a*), which sort first, and three calm ones (b*). b3's managed copy is missing."""
    titles = {}
    with unit_of_work:
        for title, mood in (("a1", "dark"), ("a2", "dark"), ("a3", "dark"), ("b1", "calm"), ("b2", "calm"), ("b3", "calm")):
            status = TrackStatus.MISSING_MANAGED_FILE if title == "b3" else TrackStatus.READY
            track = Track(
                track_id=str(uuid.uuid4()), sha256=hashlib.sha256(title.encode()).hexdigest(), size_bytes=10,
                audio_format=AudioFormat.FLAC, status=status, original_filename=f"{title}.flac", created_at=_NOW,
                updated_at=_NOW, title=title, artist=f"Artist {title}", analysis_version="test@1",
                labels=(TrackLabel(LabelKind.GENRE, "ambient", "tag", True), TrackLabel(LabelKind.MOOD, mood, "tag", True)),
            )
            unit_of_work.tracks.add(track)
            titles[title] = track.track_id
        unit_of_work.commit()
    return titles


def _titles(track_ids, ids):
    title_of = {track_id: title for title, track_id in ids.items()}
    return [title_of[track_id] for track_id in track_ids]


@pytest.fixture
def focus(playlists, listener):
    return playlists.create_playlist(listener, "Focus")


# --- Playlists ----------------------------------------------------------------------------------


def test_a_listener_creates_and_lists_playlists_with_track_counts(playlists, listener, ids, focus):
    run = playlists.create_playlist(listener, "Run")
    playlists.add_track(focus.playlist_id, ids["a1"])
    playlists.add_track(focus.playlist_id, ids["b1"])

    listed = playlists.list_playlists(listener)

    assert [(summary.playlist.name, summary.track_count) for summary in listed] == [("Focus", 2), ("Run", 0)]
    assert playlists.get_playlist(run.playlist_id).items == ()


def test_names_are_unique_per_listener(playlists, listener, focus):
    run = playlists.create_playlist(listener, "Run")

    with pytest.raises(PlaylistNameTaken):
        playlists.create_playlist(listener, " Focus ")  # trimmed, it is taken
    with pytest.raises(PlaylistNameTaken):
        playlists.rename_playlist(run.playlist_id, "Focus")

    assert playlists.rename_playlist(focus.playlist_id, "Focus").name == "Focus"  # keeping one's own name is fine
    assert [summary.playlist.name for summary in playlists.list_playlists(listener)] == ["Focus", "Run"]


def test_renaming_keeps_the_tracks(playlists, ids, focus):
    playlists.add_track(focus.playlist_id, ids["a1"])

    renamed = playlists.rename_playlist(focus.playlist_id, "Deep focus")

    contents = playlists.get_playlist(focus.playlist_id)
    assert (renamed.name, contents.playlist.name, _titles(contents.track_ids, ids)) == ("Deep focus", "Deep focus", ["a1"])
    assert renamed.updated_at > focus.updated_at


def test_a_playlist_needs_a_known_listener(playlists):
    with pytest.raises(ListenerProfileNotFound):
        playlists.create_playlist(str(uuid.uuid4()), "Focus")


@pytest.mark.parametrize(
    "call",
    [
        lambda playlists, playlist_id, track_id: playlists.get_playlist(playlist_id),
        lambda playlists, playlist_id, track_id: playlists.rename_playlist(playlist_id, "x"),
        lambda playlists, playlist_id, track_id: playlists.delete_playlist(playlist_id),
        lambda playlists, playlist_id, track_id: playlists.add_track(playlist_id, track_id),
        lambda playlists, playlist_id, track_id: playlists.remove_track(playlist_id, track_id),
        lambda playlists, playlist_id, track_id: playlists.reorder_tracks(playlist_id, []),
    ],
)
def test_unknown_playlists_are_not_found(playlists, ids, call):
    with pytest.raises(PlaylistNotFound):
        call(playlists, str(uuid.uuid4()), ids["a1"])


def test_deleting_a_playlist_keeps_the_tracks_and_the_feedback_history(playlists, sessions, recommender, listener, ids, focus, engine):
    session_id = sessions.start_session(listener, _AMBIENT).session.session_id
    queued = recommender.refresh_queue(session_id).queue[0]
    playlists.add_track(focus.playlist_id, queued.track_id, session_id, queued.occurrence_id)

    playlists.delete_playlist(focus.playlist_id)

    with pytest.raises(PlaylistNotFound):
        playlists.get_playlist(focus.playlist_id)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM tracks").scalar() == 6
        assert connection.exec_driver_sql("SELECT event_type FROM feedback_events").scalars().all() == ["PLAYLIST_ADD"]


def test_playlists_survive_a_restart(playlists, migrated_database_url, ids, focus):
    playlists.add_track(focus.playlist_id, ids["b1"])
    playlists.add_track(focus.playlist_id, ids["a2"])

    engine = create_database_engine(migrated_database_url)
    try:
        restarted = PlaylistService(SqlAlchemyUnitOfWork(create_session_factory(engine)))
        assert _titles(restarted.get_playlist(focus.playlist_id).track_ids, ids) == ["b1", "a2"]
    finally:
        engine.dispose()


# --- Tracks in a playlist --------------------------------------------------------------------------


def test_tracks_are_added_at_the_end_once_each(playlists, ids, focus):
    playlists.add_track(focus.playlist_id, ids["a1"])
    added = playlists.add_track(focus.playlist_id, ids["b2"])

    with pytest.raises(TrackAlreadyInPlaylist):
        playlists.add_track(focus.playlist_id, ids["a1"])

    assert (_titles(added.contents.track_ids, ids), added.feedback) == (["a1", "b2"], None)
    assert _titles(playlists.get_playlist(focus.playlist_id).track_ids, ids) == ["a1", "b2"]


def test_only_library_tracks_can_be_added(playlists, focus):
    with pytest.raises(TrackNotFound):
        playlists.add_track(focus.playlist_id, str(uuid.uuid4()))


def test_a_track_whose_managed_copy_is_missing_can_still_be_kept(playlists, ids, focus):
    """Availability can change (B2 repairs missing copies); it is shown when the playlist is read, not a reason to refuse."""
    assert _titles(playlists.add_track(focus.playlist_id, ids["b3"]).contents.track_ids, ids) == ["b3"]


def test_removing_a_track_closes_the_gap(playlists, ids, focus):
    for title in ("a1", "a2", "a3"):
        playlists.add_track(focus.playlist_id, ids[title])

    contents = playlists.remove_track(focus.playlist_id, ids["a2"])

    assert (_titles(contents.track_ids, ids), [item.position for item in contents.items]) == (["a1", "a3"], [0, 1])
    with pytest.raises(TrackNotInPlaylist):
        playlists.remove_track(focus.playlist_id, ids["a2"])


def test_reordering_puts_the_tracks_in_the_given_order(playlists, ids, focus):
    for title in ("a1", "a2", "a3"):
        playlists.add_track(focus.playlist_id, ids[title])

    contents = playlists.reorder_tracks(focus.playlist_id, [ids["a3"], ids["a1"], ids["a2"]])

    assert _titles(contents.track_ids, ids) == ["a3", "a1", "a2"]
    assert _titles(playlists.get_playlist(focus.playlist_id).track_ids, ids) == ["a3", "a1", "a2"]


def test_an_invalid_order_changes_nothing(playlists, ids, focus):
    for title in ("a1", "a2"):
        playlists.add_track(focus.playlist_id, ids[title])

    with pytest.raises(InvalidPlaylistOrder):
        playlists.reorder_tracks(focus.playlist_id, [ids["a2"], ids["b1"]])

    assert _titles(playlists.get_playlist(focus.playlist_id).track_ids, ids) == ["a1", "a2"]


# --- A playlist add as feedback, and no automatic saving -------------------------------------------


@pytest.fixture
def listening(sessions, recommender, listener, ids):
    """An ambient session with a1 playing and a2, a3, b1 queued."""
    session_id = sessions.start_session(listener, _AMBIENT).session.session_id
    recommender.refresh_queue(session_id)
    sessions.advance(session_id)
    state = recommender.refresh_queue(session_id)
    assert _titles([state.playing.track_id], ids) == ["a1"]
    assert _titles([occurrence.track_id for occurrence in state.queue], ids) == ["a2", "a3", "b1"]
    return session_id, state


def test_adding_a_recommendation_is_strong_positive_feedback_and_re_ranks(playlists, sessions, ids, focus, listening):
    session_id, state = listening
    calm = state.queue[2]

    added = playlists.add_track(focus.playlist_id, calm.track_id, session_id, calm.occurrence_id)

    assert _titles(added.contents.track_ids, ids) == ["b1"]
    assert (added.feedback.event.event_type, added.feedback.event.occurrence_id) == (FeedbackEventType.PLAYLIST_ADD, calm.occurrence_id)
    assert (added.feedback.event_weight, added.feedback.interpretation.basis) == (1.0, EvidenceBasis.EXPLICIT)
    queue = _titles([occurrence.track_id for occurrence in added.feedback.state.queue], ids)
    assert queue[:2] == ["b1", "b2"] and "b3" not in queue  # tracks like the saved one lead; b3's copy is missing
    assert [event.event_type for event in sessions.history(session_id).feedback_events] == [FeedbackEventType.PLAYLIST_ADD]


def test_saving_one_recommendation_to_two_playlists_is_one_piece_of_evidence(playlists, sessions, listener, ids, focus, listening):
    """The frontend's picker can save the current song to several playlists at once."""
    session_id, state = listening
    run = playlists.create_playlist(listener, "Run")
    playing = state.playing

    playlists.add_track(focus.playlist_id, playing.track_id, session_id, playing.occurrence_id)
    second = playlists.add_track(run.playlist_id, playing.track_id, session_id, playing.occurrence_id)

    assert [event.event_type for event in sessions.history(session_id).feedback_events] == [FeedbackEventType.PLAYLIST_ADD] * 2
    assert second.feedback.interpretation.weight == 1.0
    assert second.feedback.state.playing.occurrence_id == playing.occurrence_id  # a playlist add does not touch playback


def test_adding_without_a_session_is_not_feedback(playlists, sessions, ids, focus, listening):
    session_id, _ = listening

    assert playlists.add_track(focus.playlist_id, ids["b2"]).feedback is None
    assert sessions.history(session_id).feedback_events == ()


@pytest.mark.parametrize(
    "case, error",
    [
        ("another track", ValueError),
        ("another session", RecommendationOccurrenceNotFound),
        ("ended session", InvalidSessionTransition),
        ("already in the playlist", TrackAlreadyInPlaylist),
    ],
)
def test_a_refused_add_from_a_recommendation_stores_neither_item_nor_event(playlists, sessions, listener, ids, focus, listening, case, error):
    session_id, state = listening
    occurrence = state.queue[0]
    track_id = occurrence.track_id
    if case == "another track":
        track_id = ids["b2"]
    elif case == "another session":
        session_id = sessions.start_session(listener, _AMBIENT).session.session_id  # the first session ends
    elif case == "ended session":
        sessions.end_session(session_id)
    elif case == "already in the playlist":
        playlists.add_track(focus.playlist_id, track_id)
    items_before = playlists.get_playlist(focus.playlist_id).track_ids

    with pytest.raises(error):
        playlists.add_track(focus.playlist_id, track_id, session_id, occurrence.occurrence_id)

    assert playlists.get_playlist(focus.playlist_id).track_ids == items_before
    assert all(sessions.history(sid).feedback_events == () for sid in {session_id, state.session.session_id})


def test_a_recommendation_is_named_by_session_and_occurrence_together(playlists, unit_of_work, ids, focus, listening):
    session_id, state = listening
    with pytest.raises(ValueError):
        playlists.add_track(focus.playlist_id, state.playing.track_id, session_id=session_id)
    with pytest.raises(ValueError):
        PlaylistService(unit_of_work).add_track(focus.playlist_id, state.playing.track_id, session_id, state.playing.occurrence_id)


def test_a_playlist_add_cannot_be_sent_as_a_plain_reaction(feedback, listening):
    session_id, state = listening

    with pytest.raises(ValueError):
        feedback.react(session_id, state.playing.occurrence_id, FeedbackEventType.PLAYLIST_ADD)


def test_recommendations_are_never_saved_automatically(feedback, sessions, recommender, engine, listener, ids, focus, listening):
    """Likes, saves, completions, and refreshes never put a track in a playlist; only add_track() does."""
    session_id, state = listening
    feedback.react(session_id, state.playing.occurrence_id, FeedbackEventType.LIKE)
    feedback.react(session_id, state.queue[0].occurrence_id, FeedbackEventType.SAVE)
    for _ in range(3):
        playing = sessions.get_session(session_id).playing
        feedback.report_playback(session_id, playing.occurrence_id, FeedbackEventType.COMPLETE, 200.0, 200.0)
        recommender.refresh_queue(session_id)

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM playlist_items").scalar() == 0
