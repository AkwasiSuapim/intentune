"""Library routes (B8): sources, Import, Rescan, tracks, and analysis jobs, through HTTP."""

import threading

import pytest

from src.intentune.application.analysis import AnalysisService
from src.intentune.application.library_scans import LibraryScanCoordinator


def _register(client, path):
    return client.post("/api/v1/library/sources", json={"path": str(path)})


# --- Sources ---------------------------------------------------------------------------


def test_registering_a_folder_returns_its_name_and_never_its_path(client, music):
    response = _register(client, music)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"source_id", "name", "status", "created_at", "last_scanned_at"}
    assert (body["name"], body["status"], body["last_scanned_at"]) == ("music", "active", None)
    assert str(music.parent) not in response.text
    assert music.parent.as_posix() not in response.text


def test_registering_the_same_folder_again_returns_it_unchanged(client, music):
    first = _register(client, music)
    again = _register(client, music)

    assert again.status_code == 200
    assert again.json() == first.json()
    assert len(client.get("/api/v1/library/sources").json()["items"]) == 1


def test_a_path_that_is_not_a_usable_folder_is_refused_without_echoing_it(client, tmp_path, music, media_root):
    (music / "song.wav").write_bytes(b"x")
    for path in (tmp_path / "missing" / "secret-folder", music / "song.wav"):
        response = _register(client, path)

        assert response.status_code == 422
        error = response.json()["error"]
        assert (error["code"], error["message"]) == ("VALIDATION_ERROR", "The path is not an existing folder Intentune can scan.")
        assert "secret-folder" not in response.text and "song.wav" not in response.text


def test_the_managed_media_folder_cannot_become_a_source(client, media_root):
    media_root.mkdir()

    assert _register(client, media_root).status_code == 422


def test_sources_are_listed_with_whether_a_scan_is_running(client, music, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    _register(client, music)
    _register(client, other)

    body = client.get("/api/v1/library/sources").json()

    assert [source["name"] for source in body["items"]] == ["music", "other"]
    assert body["scanning"] is False


@pytest.mark.parametrize("body", [{}, {"path": ""}, {"path": "x" * 4097}, {"path": 3}, {"path": "/music", "extra": 1}])
def test_a_registration_body_is_validated(client, body):
    response = client.post("/api/v1/library/sources", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- Import and Rescan -----------------------------------------------------------------


def test_import_scans_one_source_and_answers_with_its_report(client, music, audio):
    audio.wav(music / "one.wav", seed=1, title="One", genre="Jazz")
    audio.wav(music / "two.wav", seed=2, title="Two", genre="Jazz")
    (music / "notes.txt").write_text("not audio")
    source = _register(client, music).json()

    report = client.post("/api/v1/library/import", json={"source_id": source["source_id"]})
    again = client.post("/api/v1/library/import", json={"source_id": source["source_id"]})

    assert report.status_code == 200
    assert report.json() == {
        "source_id": source["source_id"], "source_missing": False, "imported": 2, "duplicates": 0, "unchanged": 0,
        "repaired": 0, "unsupported": 0, "failed": 0, "missing": 0, "ignored": 1, "tag_failures": 0,
    }
    assert (again.json()["imported"], again.json()["unchanged"]) == (0, 2)
    assert client.get("/api/v1/library/sources").json()["items"][0]["last_scanned_at"] is not None


def test_importing_an_unknown_source_is_not_found(client):
    response = client.post("/api/v1/library/import", json={"source_id": "4c7c3d0e-2b44-4a55-9f1d-3a0e6a3c2b10"})

    assert response.status_code == 404
    error = response.json()["error"]
    assert (error["code"], error["message"]) == ("SOURCE_NOT_FOUND", "The library source does not exist.")


def test_rescan_scans_every_source(client, music, audio, tmp_path):
    other = tmp_path / "other"
    audio.wav(music / "one.wav", seed=1)
    audio.wav(other / "two.wav", seed=2)
    first = _register(client, music).json()["source_id"]
    second = _register(client, other).json()["source_id"]

    response = client.post("/api/v1/library/rescan")

    assert response.status_code == 200
    assert [(report["source_id"], report["imported"]) for report in response.json()["reports"]] == [(first, 1), (second, 1)]


def test_a_missing_source_folder_is_reported_not_raised(client, music, audio):
    audio.wav(music / "one.wav", seed=1)
    source = _register(client, music).json()
    client.post("/api/v1/library/import", json={"source_id": source["source_id"]})
    (music / "one.wav").unlink()
    music.rmdir()

    report = client.post("/api/v1/library/import", json={"source_id": source["source_id"]}).json()

    assert report["source_missing"] is True
    assert client.get("/api/v1/library/sources").json()["items"][0]["status"] == "missing"
    assert client.get("/api/v1/library/tracks").json()["items"][0]["playable"] is True


def test_a_scan_asked_for_while_another_runs_is_a_conflict(client, music, monkeypatch):
    source = _register(client, music).json()
    container = client.app.state.container
    scanning, release = threading.Event(), threading.Event()

    class HeldLibrary:
        """The startup scan, held open."""

        def rescan_library(self):
            scanning.set()
            assert release.wait(timeout=5)
            return []

    real_scans = container.scans
    monkeypatch.setattr(container, "scans", LibraryScanCoordinator(lambda: HeldLibrary()))
    assert container.scans.start_background_rescan()
    assert scanning.wait(timeout=5)
    try:
        assert client.get("/api/v1/library/sources").json()["scanning"] is True
        for response in (
            client.post("/api/v1/library/import", json={"source_id": source["source_id"]}),
            client.post("/api/v1/library/rescan"),
        ):
            assert response.status_code == 409
            error = response.json()["error"]
            assert (error["code"], error["message"]) == ("CONFLICT", "A library scan is already running. Try again when it has finished.")
    finally:
        release.set()
        assert container.scans.wait(timeout=5)

    assert client.get("/api/v1/library/sources").json()["scanning"] is False
    monkeypatch.setattr(container, "scans", real_scans)
    assert client.post("/api/v1/library/import", json={"source_id": source["source_id"]}).status_code == 200


# --- Tracks ----------------------------------------------------------------------------


def test_tracks_show_their_metadata_and_audio_url_but_no_path(client, library_tracks, music, media_root):
    track = library_tracks["a1"]

    assert set(track) == {
        "track_id", "title", "file_name", "artist", "album", "year", "duration_seconds", "format", "status",
        "playable", "genres", "moods", "audio_url",
    }
    assert (track["title"], track["file_name"], track["artist"], track["format"]) == ("a1", "a1.wav", "Artist a1", "wav")
    assert (track["status"], track["playable"], track["genres"], track["moods"]) == ("imported", True, ["Ambient"], [])
    assert track["audio_url"] == f"/api/v1/tracks/{track['track_id']}/audio"
    listing = client.get("/api/v1/library/tracks").text
    for path in (music, media_root):
        assert str(path) not in listing and path.as_posix() not in listing and str(path).replace("\\", "\\\\") not in listing


def test_tracks_are_paged(client, library_tracks):
    first = client.get("/api/v1/library/tracks", params={"limit": 4}).json()
    rest = client.get("/api/v1/library/tracks", params={"limit": 4, "offset": 4}).json()

    assert (first["total"], first["limit"], first["offset"], len(first["items"])) == (6, 4, 0, 4)
    assert (rest["offset"], len(rest["items"])) == (4, 2)
    assert {track["track_id"] for track in first["items"] + rest["items"]} == {track["track_id"] for track in library_tracks.values()}
    assert client.get("/api/v1/library/tracks", params={"offset": 10}).json()["items"] == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}, {"limit": "many"}])
def test_paging_parameters_are_bounded(client, params):
    response = client.get("/api/v1/library/tracks", params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- Analysis jobs -------------------------------------------------------------------


def test_jobs_are_listed_and_filtered_by_status(client, library_tracks):
    container = client.app.state.container
    analysis: AnalysisService = container.analysis()
    assert analysis.enqueue_pending() == 6
    analysis.process_next()

    everything = client.get("/api/v1/library/jobs").json()
    pending = client.get("/api/v1/library/jobs", params={"status": "pending"}).json()
    succeeded = client.get("/api/v1/library/jobs", params={"status": "succeeded", "limit": 1}).json()

    assert everything["total"] == 6
    assert set(everything["items"][0]) == {
        "job_id", "track_id", "kind", "analyzer", "status", "attempts", "created_at", "updated_at", "started_at",
        "finished_at", "failure_reason", "error_message",
    }
    assert everything["items"][0]["kind"] == "analyze_audio"
    assert pending["total"] == 5 and all(job["status"] == "pending" for job in pending["items"])
    assert (succeeded["total"], len(succeeded["items"]), succeeded["items"][0]["attempts"]) == (1, 1, 1)
    assert client.get("/api/v1/library/jobs", params={"status": "done"}).status_code == 422
