"""GET and HEAD /api/v1/tracks/{track_id}/audio (B8, spec §25): by id only, with the range requests browsers seek with.

These pin the installed Starlette FileResponse behavior the route relies on,
so an upgrade that changes it fails here.
"""

import pytest

from src.intentune.api.routes.tracks import MEDIA_TYPES
from src.intentune.domain.library import AudioFormat


@pytest.fixture
def track(library_tracks):
    return library_tracks["a1"]


@pytest.fixture
def managed_bytes(track, media_root):
    return (media_root / f"{track['track_id']}.wav").read_bytes()


def test_the_whole_file_is_served_with_its_media_type(client, track, managed_bytes):
    response = client.get(track["audio_url"])

    assert response.status_code == 200
    assert response.content == managed_bytes
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["accept-ranges"] == "bytes"
    assert int(response.headers["content-length"]) == len(managed_bytes)
    assert "content-disposition" not in response.headers


def test_head_answers_the_headers_without_the_body(client, track, managed_bytes):
    response = client.head(track["audio_url"])

    assert response.status_code == 200
    assert response.content == b""
    assert int(response.headers["content-length"]) == len(managed_bytes)
    assert response.headers["accept-ranges"] == "bytes"


@pytest.mark.parametrize(
    "range_header, start, end",
    [("bytes=0-9", 0, 9), ("bytes=100-", 100, None), ("bytes=-16", -16, None), ("bytes=10-999999999", 10, None)],
    ids=["closed", "open-ended", "suffix", "end-clamped"],
)
def test_a_single_range_is_partial_content(client, track, managed_bytes, range_header, start, end):
    size = len(managed_bytes)
    first = start if start >= 0 else size + start
    last = end if end is not None else size - 1

    response = client.get(track["audio_url"], headers={"Range": range_header})

    assert response.status_code == 206
    assert response.content == managed_bytes[first : last + 1]
    assert response.headers["content-range"] == f"bytes {first}-{last}/{size}"
    assert int(response.headers["content-length"]) == last - first + 1
    assert response.headers["content-type"] == "audio/wav"


def test_several_ranges_are_multipart(client, track, managed_bytes):
    response = client.get(track["audio_url"], headers={"Range": "bytes=0-3,10-13"})

    assert response.status_code == 206
    assert response.headers["content-type"].startswith("multipart/byteranges; boundary=")
    assert managed_bytes[0:4] in response.content and managed_bytes[10:14] in response.content


def test_a_range_past_the_end_is_not_satisfiable(client, track, managed_bytes):
    response = client.get(track["audio_url"], headers={"Range": f"bytes={len(managed_bytes)}-"})

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(managed_bytes)}"
    assert "x-request-id" in response.headers  # Starlette's own reply, outside the envelope, still carries the id


def test_a_malformed_range_is_a_bad_request(client, track):
    response = client.get(track["audio_url"], headers={"Range": "bytes=9-3"})

    assert response.status_code == 400
    assert "x-request-id" in response.headers


def test_every_allowlisted_format_has_an_audio_media_type():
    assert set(MEDIA_TYPES) == set(AudioFormat)
    assert all(media_type.startswith("audio/") for media_type in MEDIA_TYPES.values())


def test_flac_is_served_as_audio_flac(client, music, audio):
    audio.flac(music / "song.flac", TITLE="Song", GENRE="Jazz")
    source = client.post("/api/v1/library/sources", json={"path": str(music)}).json()
    client.post("/api/v1/library/import", json={"source_id": source["source_id"]})
    [track] = client.get("/api/v1/library/tracks").json()["items"]

    assert client.head(track["audio_url"]).headers["content-type"] == "audio/flac"


def test_an_unknown_track_is_not_found(client):
    response = client.get("/api/v1/tracks/8d4b1f0e-3a4c-4b6e-9d2f-1e0c7a5b3c21/audio")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TRACK_NOT_FOUND"


@pytest.mark.parametrize("track_id", ["..%2F..%2Fintentune-test.db", "%2E%2E", "C:%5CWindows%5Cwin.ini", "not-a-track"])
def test_a_path_in_place_of_an_id_reaches_no_file(client, library_tracks, track_id):
    response = client.get(f"/api/v1/tracks/{track_id}/audio")

    assert response.status_code == 404
    assert "content-range" not in response.headers


def test_a_track_whose_managed_copy_is_gone_is_unavailable_and_marked_so(client, track, media_root):
    (media_root / f"{track['track_id']}.wav").unlink()

    response = client.get(track["audio_url"])

    assert response.status_code == 409
    error = response.json()["error"]
    assert (error["code"], error["message"]) == ("TRACK_UNAVAILABLE", "The track's audio file is missing. Rescan the library to restore it.")
    assert str(media_root) not in response.text
    listed = {item["track_id"]: item for item in client.get("/api/v1/library/tracks").json()["items"]}[track["track_id"]]
    assert (listed["status"], listed["playable"]) == ("missing_managed_file", False)
    assert client.head(track["audio_url"]).status_code == 409


def test_a_rescan_restores_an_unavailable_track(client, track, media_root):
    (media_root / f"{track['track_id']}.wav").unlink()
    client.get(track["audio_url"])

    client.post("/api/v1/library/rescan")

    assert client.get(track["audio_url"]).status_code == 200
