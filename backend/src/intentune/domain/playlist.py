"""Playlists (Prototype 1, phase B7): the listener's own ordered collections of library tracks (D34).

Spec §9 and execution guide §10: create, rename, delete, add, remove, and
reorder. A track appears at most once in a playlist (the default until the
product approves duplicates). Recommendations are never saved to a playlist
automatically: only the listener adds tracks.

- Playlist: a named collection belonging to the local listener. Names are
  unique per listener, as the approved frontend keeps them.
- PlaylistItem: one track at one position. Positions run 0, 1, 2, ... with
  no gaps.
- PlaylistContents: a playlist with its items in order, and the pure
  operations on it: add (at the end), remove (closing the gap), and reorder
  (a permutation of the same tracks).

How a track looks or whether it can play is the library's business: a track
whose managed copy goes missing stays in its playlists. Presentation, such as
the frontend's colour tone, is not stored (D32).
"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Iterable, Tuple

from src.intentune.domain.validation import (
    new_uuid,
    require_canonical_uuid,
    require_non_negative_int,
    require_text,
    require_utc_datetime,
)

MAX_PLAYLIST_NAME_LENGTH = 100


# --- Errors ----------------------------------------------------------------------


class PlaylistError(Exception):
    """Base class for playlist errors the application layer reports to its callers."""


class PlaylistNotFound(PlaylistError, LookupError):
    pass


class PlaylistNameTaken(PlaylistError):
    """The listener already has a playlist with this name."""


class TrackAlreadyInPlaylist(PlaylistError):
    """A track appears at most once in a playlist."""


class TrackNotInPlaylist(PlaylistError, LookupError):
    pass


class InvalidPlaylistOrder(PlaylistError, ValueError):
    """A new order must list exactly the playlist's tracks, each once."""


# --- Models ----------------------------------------------------------------------


def _playlist_name(value: object) -> str:
    name = require_text(value, "name")
    if len(name) > MAX_PLAYLIST_NAME_LENGTH:
        raise ValueError(f"a playlist name is at most {MAX_PLAYLIST_NAME_LENGTH} characters")
    return name


@dataclass(frozen=True)
class Playlist:
    playlist_id: str
    listener_profile_id: str
    name: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        require_canonical_uuid(self.playlist_id, "playlist_id")
        require_canonical_uuid(self.listener_profile_id, "listener_profile_id")
        object.__setattr__(self, "name", _playlist_name(self.name))
        object.__setattr__(self, "created_at", require_utc_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", require_utc_datetime(self.updated_at, "updated_at"))
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")

    def renamed(self, name: str, now: datetime) -> "Playlist":
        return replace(self, name=name, updated_at=now)

    def touched(self, now: datetime) -> "Playlist":
        return replace(self, updated_at=now)


def new_playlist(listener_profile_id: str, name: str, now: datetime) -> Playlist:
    return Playlist(playlist_id=new_uuid(), listener_profile_id=listener_profile_id, name=name, created_at=now, updated_at=now)


@dataclass(frozen=True)
class PlaylistItem:
    playlist_id: str
    track_id: str
    position: int
    added_at: datetime

    def __post_init__(self) -> None:
        require_canonical_uuid(self.playlist_id, "playlist_id")
        require_canonical_uuid(self.track_id, "track_id")
        require_non_negative_int(self.position, "position")
        object.__setattr__(self, "added_at", require_utc_datetime(self.added_at, "added_at"))


@dataclass(frozen=True)
class PlaylistContents:
    """A playlist and its items in order. Every change returns new contents, with the playlist touched."""

    playlist: Playlist
    items: Tuple[PlaylistItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        if any(item.playlist_id != self.playlist.playlist_id for item in self.items):
            raise ValueError("every item belongs to the playlist")
        if [item.position for item in self.items] != list(range(len(self.items))):
            raise ValueError("items are in position order, from 0, without gaps")
        if len(set(self.track_ids)) != len(self.items):
            raise ValueError("a track appears at most once in a playlist")

    @property
    def track_ids(self) -> Tuple[str, ...]:
        return tuple(item.track_id for item in self.items)

    def with_track(self, track_id: str, now: datetime) -> "PlaylistContents":
        """The track added at the end."""
        if track_id in self.track_ids:
            raise TrackAlreadyInPlaylist(track_id)
        item = PlaylistItem(self.playlist.playlist_id, track_id, len(self.items), now)
        return PlaylistContents(self.playlist.touched(now), self.items + (item,))

    def without_track(self, track_id: str, now: datetime) -> "PlaylistContents":
        """The track removed; the tracks after it move up one place."""
        if track_id not in self.track_ids:
            raise TrackNotInPlaylist(track_id)
        kept = [item for item in self.items if item.track_id != track_id]
        return PlaylistContents(self.playlist.touched(now), _renumbered(kept))

    def in_order(self, track_ids: Iterable[str], now: datetime) -> "PlaylistContents":
        """The same tracks in a new order. Each keeps when it was added."""
        track_ids = list(track_ids)
        if len(track_ids) != len(self.items) or set(track_ids) != set(self.track_ids):
            raise InvalidPlaylistOrder("A new order lists exactly the playlist's tracks, each once.")
        by_track = {item.track_id: item for item in self.items}
        return PlaylistContents(self.playlist.touched(now), _renumbered(by_track[track_id] for track_id in track_ids))


def _renumbered(items: Iterable[PlaylistItem]) -> Tuple[PlaylistItem, ...]:
    return tuple(replace(item, position=position) for position, item in enumerate(items))


@dataclass(frozen=True)
class PlaylistSummary:
    """A playlist in a listing, with how many tracks it holds."""

    playlist: Playlist
    track_count: int
