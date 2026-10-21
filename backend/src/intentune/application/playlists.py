"""Application use cases for playlists (Prototype 1, phase B7).

PlaylistService covers execution guide §10. Every command runs in one
transaction through the UnitOfWork port.
- Playlists: create, rename, delete, list (with track counts), and read (the
  tracks in order).
- Their tracks: add (at the end), remove, and reorder.

A track appears at most once in a playlist, and a playlist name once per
listener.

Recommendations are never saved automatically (execution guide §10): nothing
but an explicit add_track() call puts a track in a playlist. When the listener
adds the track of a recommendation in a session, add_track() takes that
occurrence. After the item is stored, FeedbackService records a PLAYLIST_ADD
event (strong positive feedback, +1.00) and re-ranks the session's queue. The
occurrence is checked before anything is stored, so a refused add leaves
neither an item nor an event.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Optional

from src.intentune.application.feedback import FeedbackOutcome, FeedbackService
from src.intentune.domain.library import TrackNotFound
from src.intentune.domain.playlist import (
    Playlist,
    PlaylistContents,
    PlaylistNameTaken,
    PlaylistNotFound,
    PlaylistSummary,
    new_playlist,
)
from src.intentune.domain.session import (
    InvalidSessionTransition,
    ListenerProfileNotFound,
    RecommendationOccurrenceNotFound,
    SessionNotFound,
)
from src.intentune.ports.unit_of_work import UnitOfWork


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TrackAdded:
    """The playlist after the add, and, for a recommendation added from a session, what the feedback did."""

    contents: PlaylistContents
    feedback: Optional[FeedbackOutcome] = None


class PlaylistService:
    def __init__(
        self,
        unit_of_work: UnitOfWork,
        feedback: Optional[FeedbackService] = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._uow = unit_of_work
        self._feedback = feedback
        self._clock = clock

    # --- Playlists ------------------------------------------------------------------

    def create_playlist(self, listener_profile_id: str, name: str) -> Playlist:
        playlist = new_playlist(listener_profile_id, name, self._clock())
        with self._uow:
            if self._uow.listener_profiles.get(listener_profile_id) is None:
                raise ListenerProfileNotFound(listener_profile_id)
            self._require_free_name(playlist)
            self._uow.playlists.add(playlist)
            self._uow.commit()
        return playlist

    def rename_playlist(self, playlist_id: str, name: str) -> Playlist:
        now = self._clock()
        with self._uow:
            renamed = self._require_playlist(playlist_id).renamed(name, now)
            self._require_free_name(renamed)
            self._uow.playlists.save(renamed)
            self._uow.commit()
        return renamed

    def delete_playlist(self, playlist_id: str) -> None:
        """Delete the playlist and its items. The tracks stay in the library, and feedback history is kept."""
        with self._uow:
            self._require_playlist(playlist_id)
            self._uow.playlists.delete(playlist_id)
            self._uow.commit()

    def list_playlists(self, listener_profile_id: str) -> List[PlaylistSummary]:
        """The listener's playlists, oldest first, with how many tracks each holds."""
        with self._uow:
            playlists = self._uow.playlists.list_for_listener(listener_profile_id)
            counts = self._uow.playlists.track_counts(playlist.playlist_id for playlist in playlists)
        return [PlaylistSummary(playlist, counts[playlist.playlist_id]) for playlist in playlists]

    def get_playlist(self, playlist_id: str) -> PlaylistContents:
        with self._uow:
            return self._contents(self._require_playlist(playlist_id))

    # --- Tracks in a playlist -------------------------------------------------------

    def add_track(
        self,
        playlist_id: str,
        track_id: str,
        session_id: Optional[str] = None,
        occurrence_id: Optional[str] = None,
    ) -> TrackAdded:
        """Add a library track at the end of the playlist.

        Pass session_id and occurrence_id when the listener adds a recommendation from
        a listening session: the add is then also recorded as PLAYLIST_ADD feedback,
        and the session's queue is re-ranked.
        """
        if (session_id is None) != (occurrence_id is None):
            raise ValueError("A recommendation is named by its session and occurrence together.")
        if occurrence_id is not None and self._feedback is None:
            raise ValueError("Recording a playlist add as feedback needs a FeedbackService.")

        now = self._clock()
        with self._uow:
            playlist = self._require_playlist(playlist_id)
            if self._uow.tracks.get(track_id) is None:
                raise TrackNotFound(track_id)
            if occurrence_id is not None:
                self._require_recommendation_of(session_id, occurrence_id, track_id)
            contents = self._contents(playlist).with_track(track_id, now)
            self._store(contents)
            self._uow.commit()

        feedback = self._feedback.record_playlist_add(session_id, occurrence_id) if occurrence_id is not None else None
        return TrackAdded(contents=contents, feedback=feedback)

    def remove_track(self, playlist_id: str, track_id: str) -> PlaylistContents:
        """Remove a track; the tracks after it move up one place. Removing is not feedback."""
        now = self._clock()
        with self._uow:
            contents = self._contents(self._require_playlist(playlist_id)).without_track(track_id, now)
            self._store(contents)
            self._uow.commit()
        return contents

    def reorder_tracks(self, playlist_id: str, track_ids: Iterable[str]) -> PlaylistContents:
        """Put the playlist's tracks in this order. It must list exactly the playlist's tracks, each once."""
        now = self._clock()
        with self._uow:
            contents = self._contents(self._require_playlist(playlist_id)).in_order(track_ids, now)
            self._store(contents)
            self._uow.commit()
        return contents

    # --- Internals (inside the caller's transaction) -----------------------------------

    def _require_playlist(self, playlist_id: str) -> Playlist:
        playlist = self._uow.playlists.get(playlist_id)
        if playlist is None:
            raise PlaylistNotFound(playlist_id)
        return playlist

    def _require_free_name(self, playlist: Playlist) -> None:
        holder = self._uow.playlists.get_by_name(playlist.listener_profile_id, playlist.name)
        if holder is not None and holder.playlist_id != playlist.playlist_id:
            raise PlaylistNameTaken(playlist.name)

    def _require_recommendation_of(self, session_id: str, occurrence_id: str, track_id: str) -> None:
        session = self._uow.listening_sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        if not session.is_active:
            raise InvalidSessionTransition("The session has ended. Start a new session to keep listening.")
        occurrence = self._uow.recommendation_occurrences.get(occurrence_id)
        if occurrence is None or occurrence.session_id != session_id:
            raise RecommendationOccurrenceNotFound(occurrence_id)
        if occurrence.track_id != track_id:
            raise ValueError("The recommendation named is of another track.")

    def _contents(self, playlist: Playlist) -> PlaylistContents:
        return PlaylistContents(playlist, tuple(self._uow.playlists.items(playlist.playlist_id)))

    def _store(self, contents: PlaylistContents) -> None:
        self._uow.playlists.replace_items(contents.playlist.playlist_id, contents.items)
        self._uow.playlists.save(contents.playlist)
