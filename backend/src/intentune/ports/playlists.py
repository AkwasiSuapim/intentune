"""Playlist storage port (Prototype 1, phase B7). Implemented in persistence/repositories.py."""

from typing import Dict, Iterable, List, Optional, Protocol, Sequence

from src.intentune.domain.playlist import Playlist, PlaylistItem


class PlaylistRepository(Protocol):
    def get(self, playlist_id: str) -> Optional[Playlist]:
        ...

    def get_by_name(self, listener_profile_id: str, name: str) -> Optional[Playlist]:
        ...

    def list_for_listener(self, listener_profile_id: str) -> List[Playlist]:
        """The listener's playlists, oldest first."""
        ...

    def track_counts(self, playlist_ids: Iterable[str]) -> Dict[str, int]:
        """How many tracks each playlist holds (0 for an empty one)."""
        ...

    def add(self, playlist: Playlist) -> None:
        ...

    def save(self, playlist: Playlist) -> None:
        ...

    def delete(self, playlist_id: str) -> None:
        """Remove the playlist and its items. The tracks themselves stay in the library."""
        ...

    def items(self, playlist_id: str) -> List[PlaylistItem]:
        """The playlist's items in position order."""
        ...

    def replace_items(self, playlist_id: str, items: Sequence[PlaylistItem]) -> None:
        """Make these the playlist's items, in this order."""
        ...
