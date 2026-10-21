"""Playlist domain tests: pure, no database (Prototype 1, phase B7).

Covers the playlist and item invariants and the three pure operations
(add at the end, remove closing the gap, reorder as a permutation), with
"one entry per track per playlist" as the rule (execution guide §10).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.intentune.domain.playlist import (
    MAX_PLAYLIST_NAME_LENGTH,
    InvalidPlaylistOrder,
    Playlist,
    PlaylistContents,
    PlaylistItem,
    TrackAlreadyInPlaylist,
    TrackNotInPlaylist,
    new_playlist,
)

_NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
_LATER = _NOW + timedelta(minutes=5)
_LISTENER = str(uuid.uuid4())
_TRACKS = [str(uuid.uuid4()) for _ in range(4)]


def _playlist(**overrides):
    values = dict(playlist_id=str(uuid.uuid4()), listener_profile_id=_LISTENER, name="Focus", created_at=_NOW, updated_at=_NOW)
    values.update(overrides)
    return Playlist(**values)


def _contents(*track_ids):
    playlist = _playlist()
    items = tuple(PlaylistItem(playlist.playlist_id, track_id, position, _NOW) for position, track_id in enumerate(track_ids))
    return PlaylistContents(playlist, items)


# --- Playlists -----------------------------------------------------------------------------


def test_a_new_playlist_has_an_identity_a_trimmed_name_and_utc_times():
    playlist = new_playlist(_LISTENER, "  Late night  ", _NOW)

    assert uuid.UUID(playlist.playlist_id).version == 4
    assert (playlist.name, playlist.created_at, playlist.updated_at) == ("Late night", _NOW, _NOW)


def test_a_name_may_use_the_whole_length_and_no_more():
    assert len(_playlist(name="x" * MAX_PLAYLIST_NAME_LENGTH).name) == MAX_PLAYLIST_NAME_LENGTH
    with pytest.raises(ValueError):
        _playlist(name="x" * (MAX_PLAYLIST_NAME_LENGTH + 1))


@pytest.mark.parametrize(
    "overrides",
    [
        dict(name=""),
        dict(name="   "),
        dict(name=None),
        dict(playlist_id="1"),
        dict(listener_profile_id="listener"),
        dict(created_at=datetime(2026, 10, 21, 9, 0)),  # naive
        dict(updated_at=_NOW - timedelta(seconds=1)),
    ],
)
def test_playlist_invariants(overrides):
    with pytest.raises(ValueError):
        _playlist(**overrides)


def test_renaming_keeps_the_identity_and_moves_updated_at():
    playlist = _playlist()

    renamed = playlist.renamed(" Run ", _LATER)

    assert (renamed.playlist_id, renamed.name, renamed.created_at, renamed.updated_at) == (playlist.playlist_id, "Run", _NOW, _LATER)


# --- Items and contents ---------------------------------------------------------------------


def test_an_item_position_cannot_be_negative():
    with pytest.raises(ValueError):
        PlaylistItem(str(uuid.uuid4()), _TRACKS[0], -1, _NOW)


@pytest.mark.parametrize(
    "positions, track_ids",
    [((0, 2), _TRACKS[:2]), ((1,), _TRACKS[:1]), ((1, 0), _TRACKS[:2]), ((0, 1), [_TRACKS[0], _TRACKS[0]])],
)
def test_contents_have_one_entry_per_track_in_position_order_without_gaps(positions, track_ids):
    playlist = _playlist()
    items = tuple(PlaylistItem(playlist.playlist_id, track_id, position, _NOW) for position, track_id in zip(positions, track_ids))

    with pytest.raises(ValueError):
        PlaylistContents(playlist, items)


def test_contents_hold_only_their_own_playlists_items():
    with pytest.raises(ValueError):
        PlaylistContents(_playlist(), (PlaylistItem(str(uuid.uuid4()), _TRACKS[0], 0, _NOW),))


def test_adding_puts_the_track_at_the_end_and_touches_the_playlist():
    contents = _contents(*_TRACKS[:2])

    added = contents.with_track(_TRACKS[2], _LATER)

    assert added.track_ids == tuple(_TRACKS[:3])
    assert (added.items[-1].position, added.items[-1].added_at) == (2, _LATER)
    assert added.playlist.updated_at == _LATER


def test_a_track_appears_at_most_once():
    with pytest.raises(TrackAlreadyInPlaylist):
        _contents(*_TRACKS[:2]).with_track(_TRACKS[1], _LATER)


def test_removing_closes_the_gap():
    removed = _contents(*_TRACKS).without_track(_TRACKS[1], _LATER)

    assert removed.track_ids == (_TRACKS[0], _TRACKS[2], _TRACKS[3])
    assert [item.position for item in removed.items] == [0, 1, 2]
    assert removed.playlist.updated_at == _LATER


def test_removing_a_track_not_in_the_playlist_is_refused():
    with pytest.raises(TrackNotInPlaylist):
        _contents(*_TRACKS[:2]).without_track(_TRACKS[3], _LATER)


def test_reordering_moves_tracks_and_keeps_when_each_was_added():
    contents = _contents(*_TRACKS[:3]).with_track(_TRACKS[3], _LATER)
    order = [_TRACKS[3], _TRACKS[0], _TRACKS[2], _TRACKS[1]]

    reordered = contents.in_order(order, _LATER + timedelta(minutes=1))

    assert reordered.track_ids == tuple(order)
    assert [item.position for item in reordered.items] == [0, 1, 2, 3]
    assert [item.added_at for item in reordered.items] == [_LATER, _NOW, _NOW, _NOW]


@pytest.mark.parametrize(
    "order",
    [
        [_TRACKS[1], _TRACKS[0]],  # a track missing
        [_TRACKS[1], _TRACKS[0], _TRACKS[2], _TRACKS[3]],  # a track not in the playlist
        [_TRACKS[1], _TRACKS[0], _TRACKS[0]],  # a track twice, another missing
        [_TRACKS[1], _TRACKS[0], _TRACKS[2], _TRACKS[0]],  # every track, one of them twice
        [],
    ],
)
def test_a_new_order_must_list_exactly_the_playlists_tracks(order):
    with pytest.raises(InvalidPlaylistOrder):
        _contents(*_TRACKS[:3]).in_order(order, _LATER)


def test_an_empty_playlist_can_be_reordered_to_itself():
    assert _contents().in_order([], _LATER).items == ()
