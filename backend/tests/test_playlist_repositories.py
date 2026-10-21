"""Playlist repository tests against a migrated SQLite database (Prototype 1, phase B7).

Covers round trips, the order of items, whole-list replacement (two tracks
can swap places without breaking the unique positions), restart persistence,
and the database rules that back the domain: one name per listener, one entry
per track per playlist, unique non-negative positions, and foreign keys to
real listeners, playlists, and tracks. A test pins the exact columns: no
presentation state, such as the frontend's colour tone, is stored (D32).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.domain.library import AudioFormat, Track, TrackStatus
from src.intentune.domain.listener import ListenerProfile
from src.intentune.domain.playlist import PlaylistItem, new_playlist
from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork

_NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def listener(unit_of_work):
    return ensure_default_listener(unit_of_work).listener_profile_id


@pytest.fixture
def tracks(unit_of_work):
    created = []
    with unit_of_work:
        for char in "abcd":
            track = Track(
                track_id=str(uuid.uuid4()), sha256=char * 64, size_bytes=10, audio_format=AudioFormat.FLAC,
                status=TrackStatus.IMPORTED, original_filename=f"{char}.flac", created_at=_NOW, updated_at=_NOW,
            )
            unit_of_work.tracks.add(track)
            created.append(track.track_id)
        unit_of_work.commit()
    return created


def _add(unit_of_work, playlist, *track_ids):
    with unit_of_work:
        unit_of_work.playlists.add(playlist)
        unit_of_work.playlists.replace_items(
            playlist.playlist_id, [PlaylistItem(playlist.playlist_id, track_id, position, _NOW) for position, track_id in enumerate(track_ids)]
        )
        unit_of_work.commit()
    return playlist


def test_playlists_and_their_items_round_trip_in_order(unit_of_work, listener, tracks):
    playlist = _add(unit_of_work, new_playlist(listener, "Focus", _NOW), tracks[2], tracks[0], tracks[1])

    with unit_of_work:
        loaded = unit_of_work.playlists.get(playlist.playlist_id)
        items = unit_of_work.playlists.items(playlist.playlist_id)
        by_name = unit_of_work.playlists.get_by_name(listener, "Focus")

    assert loaded == playlist == by_name
    assert [(item.track_id, item.position, item.added_at) for item in items] == [(tracks[2], 0, _NOW), (tracks[0], 1, _NOW), (tracks[1], 2, _NOW)]


def test_unknown_playlists_and_names_are_absent(unit_of_work, listener):
    with unit_of_work:
        assert unit_of_work.playlists.get(str(uuid.uuid4())) is None
        assert unit_of_work.playlists.get_by_name(listener, "Nothing") is None
        assert unit_of_work.playlists.items(str(uuid.uuid4())) == []


def test_a_listener_lists_their_playlists_oldest_first_with_track_counts(unit_of_work, listener, tracks):
    older = _add(unit_of_work, new_playlist(listener, "B", _NOW), tracks[0], tracks[1])
    newer = _add(unit_of_work, new_playlist(listener, "A", _NOW + timedelta(seconds=1)))

    with unit_of_work:
        listed = unit_of_work.playlists.list_for_listener(listener)
        counts = unit_of_work.playlists.track_counts([older.playlist_id, newer.playlist_id])

    assert [playlist.playlist_id for playlist in listed] == [older.playlist_id, newer.playlist_id]
    assert counts == {older.playlist_id: 2, newer.playlist_id: 0}


def test_saving_renames_and_replacing_items_can_swap_positions(unit_of_work, listener, tracks):
    playlist = _add(unit_of_work, new_playlist(listener, "Focus", _NOW), tracks[0], tracks[1])
    swapped = [PlaylistItem(playlist.playlist_id, tracks[1], 0, _NOW), PlaylistItem(playlist.playlist_id, tracks[0], 1, _NOW)]

    with unit_of_work:
        unit_of_work.playlists.save(playlist.renamed("Deep focus", _NOW + timedelta(minutes=1)))
        unit_of_work.playlists.replace_items(playlist.playlist_id, swapped)
        unit_of_work.commit()

    with unit_of_work:
        assert unit_of_work.playlists.get(playlist.playlist_id).name == "Deep focus"
        assert [item.track_id for item in unit_of_work.playlists.items(playlist.playlist_id)] == [tracks[1], tracks[0]]


def test_deleting_a_playlist_removes_its_items_and_keeps_the_tracks(unit_of_work, engine, listener, tracks):
    playlist = _add(unit_of_work, new_playlist(listener, "Focus", _NOW), tracks[0], tracks[1])

    with unit_of_work:
        unit_of_work.playlists.delete(playlist.playlist_id)
        unit_of_work.commit()

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM playlist_items").scalar() == 0
        assert connection.exec_driver_sql("SELECT count(*) FROM playlists").scalar() == 0
        assert connection.exec_driver_sql("SELECT count(*) FROM tracks").scalar() == 4


def test_replacing_items_refuses_another_playlists_items(unit_of_work, listener, tracks):
    playlist = _add(unit_of_work, new_playlist(listener, "Focus", _NOW))

    with pytest.raises(ValueError):
        with unit_of_work:
            unit_of_work.playlists.replace_items(playlist.playlist_id, [PlaylistItem(str(uuid.uuid4()), tracks[0], 0, _NOW)])


def test_playlists_survive_a_restart(migrated_database_url, listener, tracks, unit_of_work):
    playlist = _add(unit_of_work, new_playlist(listener, "Focus", _NOW), tracks[0])

    engine = create_database_engine(migrated_database_url)
    try:
        fresh = SqlAlchemyUnitOfWork(create_session_factory(engine))
        with fresh:
            assert fresh.playlists.get(playlist.playlist_id) == playlist
            assert [item.track_id for item in fresh.playlists.items(playlist.playlist_id)] == [tracks[0]]
    finally:
        engine.dispose()


# --- Database rules -------------------------------------------------------------------------


def test_a_listener_cannot_have_two_playlists_with_one_name(unit_of_work, listener):
    _add(unit_of_work, new_playlist(listener, "Focus", _NOW))

    with pytest.raises(IntegrityError):
        _add(unit_of_work, new_playlist(listener, "Focus", _NOW))


def test_two_listeners_may_use_the_same_name(unit_of_work, listener):
    other = ListenerProfile(listener_profile_id=str(uuid.uuid4()), is_default=False, created_at=_NOW)
    with unit_of_work:
        unit_of_work.listener_profiles.add(other)
        unit_of_work.commit()

    _add(unit_of_work, new_playlist(listener, "Focus", _NOW))
    _add(unit_of_work, new_playlist(other.listener_profile_id, "Focus", _NOW))


@pytest.mark.parametrize(
    "sql, parameters",
    [
        # the same track twice in one playlist
        ("INSERT INTO playlist_items (playlist_id, track_id, position, added_at) VALUES (?, ?, 1, '2026-10-21 09:00:00')", ("playlist", "track0")),
        # a second track at a taken position
        ("INSERT INTO playlist_items (playlist_id, track_id, position, added_at) VALUES (?, ?, 0, '2026-10-21 09:00:00')", ("playlist", "track1")),
        # a negative position
        ("INSERT INTO playlist_items (playlist_id, track_id, position, added_at) VALUES (?, ?, -1, '2026-10-21 09:00:00')", ("playlist", "track1")),
        # a track that does not exist
        ("INSERT INTO playlist_items (playlist_id, track_id, position, added_at) VALUES (?, ?, 1, '2026-10-21 09:00:00')", ("playlist", "ghost")),
        # a playlist that does not exist
        ("INSERT INTO playlist_items (playlist_id, track_id, position, added_at) VALUES (?, ?, 0, '2026-10-21 09:00:00')", ("ghost", "track1")),
        # an empty name, and one too long
        ("UPDATE playlists SET name = '' WHERE id = ?", ("playlist",)),
        ("UPDATE playlists SET name = ? WHERE id = ?", ("x" * 101, "playlist")),
        # a listener that does not exist
        ("UPDATE playlists SET listener_profile_id = ? WHERE id = ?", ("ghost", "playlist")),
    ],
)
def test_database_refuses_playlist_rows_the_domain_would_not_create(engine, unit_of_work, listener, tracks, sql, parameters):
    playlist = _add(unit_of_work, new_playlist(listener, "Focus", _NOW), tracks[0])
    known = {"playlist": playlist.playlist_id, "track0": tracks[0], "track1": tracks[1], "ghost": str(uuid.uuid4())}

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(sql, tuple(known.get(value, value) for value in parameters))


def test_playlist_tables_hold_no_presentation_state(engine):
    inspector = inspect(engine)

    assert {column["name"] for column in inspector.get_columns("playlists")} == {"id", "listener_profile_id", "name", "created_at", "updated_at"}
    assert {column["name"] for column in inspector.get_columns("playlist_items")} == {"playlist_id", "track_id", "position", "added_at"}
