"""Playlist routes (B8): create, read, rename, delete, and add, remove, and reorder tracks, through HTTP."""

import pytest

_UNKNOWN = "5e0f2c1a-7b3d-4e6f-9a8b-1c2d3e4f5a6b"


def _create(client, name="Evening"):
    response = client.post("/api/v1/playlists", json={"name": name})
    assert response.status_code == 201
    return response.json()


def _add(client, playlist_id, track_id, **recommendation):
    return client.post(f"/api/v1/playlists/{playlist_id}/items", json={"track_id": track_id, **recommendation})


def _item_titles(playlist):
    return [item["track"]["title"] for item in playlist["items"]]


def _error(response):
    return response.json()["error"]


def test_a_new_playlist_is_empty_and_listed(client):
    created = _create(client)

    assert set(created) == {"playlist_id", "name", "created_at", "updated_at", "items"}
    assert (created["name"], created["items"]) == ("Evening", [])
    listing = client.get("/api/v1/playlists").json()["items"]
    assert listing == [
        {"playlist_id": created["playlist_id"], "name": "Evening", "track_count": 0, "created_at": created["created_at"], "updated_at": created["updated_at"]}
    ]


def test_playlist_names_are_trimmed_unique_and_bounded(client):
    _create(client, "  Evening  ")

    taken = client.post("/api/v1/playlists", json={"name": "Evening"})
    assert taken.status_code == 409
    assert (_error(taken)["code"], _error(taken)["message"]) == ("CONFLICT", "You already have a playlist with this name.")
    for name in ("", "   ", "x" * 101, 5, None):
        assert client.post("/api/v1/playlists", json={"name": name}).status_code == 422
    assert client.post("/api/v1/playlists", json={"name": "x" * 100}).status_code == 201


def test_tracks_are_added_at_the_end_and_shown_in_order(client, library_tracks):
    playlist_id = _create(client)["playlist_id"]

    first = _add(client, playlist_id, library_tracks["j2"]["track_id"])
    second = _add(client, playlist_id, library_tracks["a1"]["track_id"])

    assert first.status_code == 201
    assert first.json()["feedback"] is None  # not from a session: not feedback
    playlist = second.json()["playlist"]
    assert _item_titles(playlist) == ["j2", "a1"]
    assert [item["position"] for item in playlist["items"]] == [0, 1]
    assert playlist["items"][1]["track"] == library_tracks["a1"]
    assert client.get(f"/api/v1/playlists/{playlist_id}").json() == playlist
    assert client.get("/api/v1/playlists").json()["items"][0]["track_count"] == 2


def test_a_track_appears_once_and_must_exist(client, library_tracks):
    playlist_id = _create(client)["playlist_id"]
    _add(client, playlist_id, library_tracks["a1"]["track_id"])

    again = _add(client, playlist_id, library_tracks["a1"]["track_id"])
    unknown = _add(client, playlist_id, _UNKNOWN)

    assert again.status_code == 409
    assert (_error(again)["code"], _error(again)["message"]) == ("CONFLICT", "The track is already in this playlist.")
    assert unknown.status_code == 404
    assert _error(unknown)["code"] == "TRACK_NOT_FOUND"


def test_adding_a_recommendation_is_feedback_on_its_session(client, library_tracks):
    session = client.post("/api/v1/sessions", json={"context": {"temporary_genres": ["Ambient"]}}).json()
    session_id = session["session"]["session_id"]
    playing = client.post(f"/api/v1/sessions/{session_id}/turns", json={"kind": "next"}).json()["state"]["playing"]
    playlist_id = _create(client)["playlist_id"]

    response = _add(client, playlist_id, playing["track"]["track_id"], session_id=session_id, occurrence_id=playing["occurrence_id"])

    assert response.status_code == 201
    feedback = response.json()["feedback"]
    assert (feedback["event"]["event_type"], feedback["event_weight"]) == ("playlist_add", 1.0)
    assert (feedback["interpretation"]["weight"], feedback["interpretation"]["basis"]) == (1.0, "explicit")
    assert feedback["state"]["session"]["session_id"] == session_id
    assert _item_titles(response.json()["playlist"]) == [playing["track"]["title"]]
    events = client.get(f"/api/v1/sessions/{session_id}").json()["feedback_events"]
    assert [event["event_type"] for event in events] == ["playlist_add"]


def test_a_recommendation_is_named_by_its_session_and_occurrence_together(client, library_tracks):
    session_id = client.post("/api/v1/sessions", json={"context": {}}).json()["session"]["session_id"]
    playlist_id = _create(client)["playlist_id"]

    response = _add(client, playlist_id, library_tracks["a1"]["track_id"], session_id=session_id)

    assert response.status_code == 422
    assert _error(response)["message"] == "A recommendation is named by its session and occurrence together."
    assert client.get(f"/api/v1/playlists/{playlist_id}").json()["items"] == []


def test_a_recommendation_of_another_track_is_refused_and_nothing_is_stored(client, library_tracks):
    session = client.post("/api/v1/sessions", json={"context": {"temporary_genres": ["Ambient"]}}).json()
    occurrence = session["queue"][0]
    other = next(track for title, track in library_tracks.items() if title != occurrence["track"]["title"])
    playlist_id = _create(client)["playlist_id"]

    response = _add(client, playlist_id, other["track_id"], session_id=session["session"]["session_id"], occurrence_id=occurrence["occurrence_id"])

    assert response.status_code == 422
    assert client.get(f"/api/v1/playlists/{playlist_id}").json()["items"] == []
    assert client.get(f"/api/v1/sessions/{session['session']['session_id']}").json()["feedback_events"] == []


def test_a_playlist_is_renamed(client):
    playlist_id = _create(client)["playlist_id"]
    _create(client, "Morning")

    renamed = client.patch(f"/api/v1/playlists/{playlist_id}", json={"name": "Late night"})
    taken = client.patch(f"/api/v1/playlists/{playlist_id}", json={"name": "Morning"})

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Late night"
    assert taken.status_code == 409
    assert client.patch(f"/api/v1/playlists/{playlist_id}", json={"name": "Late night"}).status_code == 200  # its own name


def test_tracks_are_removed_and_the_rest_move_up(client, library_tracks):
    playlist_id = _create(client)["playlist_id"]
    for title in ("a1", "a2", "a3"):
        _add(client, playlist_id, library_tracks[title]["track_id"])

    response = client.delete(f"/api/v1/playlists/{playlist_id}/items/{library_tracks['a2']['track_id']}")
    absent = client.delete(f"/api/v1/playlists/{playlist_id}/items/{library_tracks['j1']['track_id']}")

    assert response.status_code == 200
    assert _item_titles(response.json()) == ["a1", "a3"]
    assert [item["position"] for item in response.json()["items"]] == [0, 1]
    assert absent.status_code == 404
    assert (_error(absent)["code"], _error(absent)["message"]) == ("TRACK_NOT_FOUND", "The track is not in this playlist.")


def test_tracks_are_reordered_only_by_a_full_order(client, library_tracks):
    playlist_id = _create(client)["playlist_id"]
    ids = [library_tracks[title]["track_id"] for title in ("a1", "a2", "a3")]
    for track_id in ids:
        _add(client, playlist_id, track_id)

    reordered = client.patch(f"/api/v1/playlists/{playlist_id}/items/order", json={"track_ids": ids[::-1]})

    assert reordered.status_code == 200
    assert _item_titles(reordered.json()) == ["a3", "a2", "a1"]
    for order in (ids[:2], ids + [ids[0]], [ids[0], ids[1], library_tracks["j1"]["track_id"]], []):
        response = client.patch(f"/api/v1/playlists/{playlist_id}/items/order", json={"track_ids": order})
        assert response.status_code == 422
        assert _error(response)["code"] == "VALIDATION_ERROR"
    assert _item_titles(client.get(f"/api/v1/playlists/{playlist_id}").json()) == ["a3", "a2", "a1"]


def test_a_deleted_playlist_is_gone_and_its_tracks_stay_in_the_library(client, library_tracks):
    playlist_id = _create(client)["playlist_id"]
    _add(client, playlist_id, library_tracks["a1"]["track_id"])

    response = client.delete(f"/api/v1/playlists/{playlist_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/api/v1/playlists/{playlist_id}").status_code == 404
    assert client.delete(f"/api/v1/playlists/{playlist_id}").status_code == 404
    assert client.get("/api/v1/library/tracks").json()["total"] == 6


@pytest.mark.parametrize(
    "request_args",
    [
        ("get", "/api/v1/playlists/{id}", None),
        ("patch", "/api/v1/playlists/{id}", {"name": "x"}),
        ("delete", "/api/v1/playlists/{id}", None),
        ("post", "/api/v1/playlists/{id}/items", {"track_id": _UNKNOWN}),
        ("delete", "/api/v1/playlists/{id}/items/" + _UNKNOWN, None),
        ("patch", "/api/v1/playlists/{id}/items/order", {"track_ids": []}),
    ],
    ids=["get", "rename", "delete", "add", "remove", "reorder"],
)
def test_an_unknown_playlist_is_not_found(client, request_args):
    method, path, body = request_args

    response = client.request(method, path.format(id=_UNKNOWN), json=body)

    assert response.status_code == 404
    error = _error(response)
    assert (error["code"], error["message"]) == ("PLAYLIST_NOT_FOUND", "The playlist does not exist.")
