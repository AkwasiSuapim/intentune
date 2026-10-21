"""Playlists and their tracks (B8). Playlists belong to the local listener (D01).

Adding a track with a session_id and occurrence_id says it is a
recommendation of that session: the add is then also PLAYLIST_ADD feedback,
and the answer carries what that feedback did to the session. Nothing is
ever added automatically.
"""

from fastapi import APIRouter, Response

from src.intentune.api import views
from src.intentune.api.container import Container
from src.intentune.api.dependencies import ERROR_RESPONSES, ContainerDep
from src.intentune.api.schemas import (
    AddPlaylistItemIn,
    PlaylistItemAddedOut,
    PlaylistListOut,
    PlaylistNameIn,
    PlaylistOrderIn,
    PlaylistOut,
)
from src.intentune.domain.playlist import PlaylistContents

router = APIRouter(prefix="/api/v1/playlists", tags=["playlists"], responses=ERROR_RESPONSES)


def _playlist_out(container: Container, contents: PlaylistContents) -> PlaylistOut:
    return views.playlist_out(contents, container.library().get_tracks(contents.track_ids))


@router.get("", response_model=PlaylistListOut)
def list_playlists(container: ContainerDep) -> PlaylistListOut:
    """The listener's playlists, oldest first, with how many tracks each holds."""
    playlists = container.playlists().list_playlists(container.listener_profile_id)
    return PlaylistListOut(items=[views.playlist_summary_out(summary) for summary in playlists])


@router.post("", response_model=PlaylistOut, status_code=201)
def create_playlist(body: PlaylistNameIn, container: ContainerDep) -> PlaylistOut:
    playlists = container.playlists()
    playlist = playlists.create_playlist(container.listener_profile_id, body.name)
    return _playlist_out(container, playlists.get_playlist(playlist.playlist_id))


@router.get("/{playlist_id}", response_model=PlaylistOut)
def get_playlist(playlist_id: str, container: ContainerDep) -> PlaylistOut:
    return _playlist_out(container, container.playlists().get_playlist(playlist_id))


@router.patch("/{playlist_id}", response_model=PlaylistOut)
def rename_playlist(playlist_id: str, body: PlaylistNameIn, container: ContainerDep) -> PlaylistOut:
    playlists = container.playlists()
    playlists.rename_playlist(playlist_id, body.name)
    return _playlist_out(container, playlists.get_playlist(playlist_id))


@router.delete("/{playlist_id}", status_code=204, response_class=Response)
def delete_playlist(playlist_id: str, container: ContainerDep) -> Response:
    """Delete the playlist. Its tracks stay in the library, and feedback history is kept."""
    container.playlists().delete_playlist(playlist_id)
    return Response(status_code=204)


@router.post("/{playlist_id}/items", response_model=PlaylistItemAddedOut, status_code=201)
def add_track(playlist_id: str, body: AddPlaylistItemIn, container: ContainerDep) -> PlaylistItemAddedOut:
    added = container.playlists().add_track(playlist_id, body.track_id, body.session_id, body.occurrence_id)
    track_ids = list(added.contents.track_ids)
    if added.feedback is not None:
        track_ids += views.track_ids_of(added.feedback.state)
    tracks = container.library().get_tracks(track_ids)
    return PlaylistItemAddedOut(
        playlist=views.playlist_out(added.contents, tracks),
        feedback=views.feedback_out(added.feedback, tracks) if added.feedback is not None else None,
    )


@router.delete("/{playlist_id}/items/{track_id}", response_model=PlaylistOut)
def remove_track(playlist_id: str, track_id: str, container: ContainerDep) -> PlaylistOut:
    return _playlist_out(container, container.playlists().remove_track(playlist_id, track_id))


@router.patch("/{playlist_id}/items/order", response_model=PlaylistOut)
def reorder_tracks(playlist_id: str, body: PlaylistOrderIn, container: ContainerDep) -> PlaylistOut:
    """Put the playlist's tracks in this order. It must list exactly the playlist's tracks, each once."""
    return _playlist_out(container, container.playlists().reorder_tracks(playlist_id, body.track_ids))
