"""B11: restart and upgrade on a populated database (spec §30 items 13 and 14; execution guide §14).

A restart keeps the library and its metadata, playlists, feedback, history, and the long-term profile, and listening
starts fresh: the session left open ends as app_restarted, nothing of its queue resumes, and a new session ranks the
library as it is. A database written at the first library migration upgrades to head with its data, and the app
serves it.
"""

import random

from alembic import command
from starlette.testclient import TestClient

from src.intentune.api.app import create_app
from src.intentune.application.adaptation import LongTermAdaptationService
from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.migrations import alembic_config
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork


class _NeverExplore(random.Random):
    def random(self):
        return 0.999


def _long_term(database_url, listener_profile_id):
    engine = create_database_engine(database_url)
    try:
        adaptation = LongTermAdaptationService(SqlAlchemyUnitOfWork(create_session_factory(engine)))
        return adaptation.profile(listener_profile_id), adaptation.adjustments(listener_profile_id)
    finally:
        engine.dispose()


def _like_two(client, session_id):
    """Play, then Like what plays and what is next: two strong signals about two tracks."""
    state = client.post(f"/api/v1/sessions/{session_id}/turns", json={"kind": "next"}).json()["state"]
    for occurrence in (state["playing"], state["queue"][0]):
        response = client.post(f"/api/v1/sessions/{session_id}/recommendations/{occurrence['occurrence_id']}/reactions", json={"reaction": "like"})
        assert response.status_code == 201


def _everything(client, session_ids, playlist_id):
    return {
        "tracks": client.get("/api/v1/library/tracks").json(),
        "playlist": client.get(f"/api/v1/playlists/{playlist_id}").json(),
        "history": {
            session_id: {key: value for key, value in client.get(f"/api/v1/sessions/{session_id}").json().items() if key in ("turns", "feedback_events")}
            for session_id in session_ids
        },
    }


def test_a_restart_keeps_everything_and_listening_starts_fresh(api_settings, music, audio):
    for seed, (title, genre) in enumerate((("a1", "Ambient"), ("a2", "Ambient"), ("j1", "Jazz"), ("j2", "Jazz"), ("j3", "Jazz")), start=1):
        audio.wav(music / f"{title}.wav", seed=seed, title=title, artist=f"Artist {title}", genre=genre)
    first_run = create_app(api_settings, rng_factory=lambda: _NeverExplore(0))
    with TestClient(first_run) as client:
        listener = first_run.state.container.listener_profile_id
        source = client.post("/api/v1/library/sources", json={"path": str(music)}).json()
        assert client.post("/api/v1/library/import", json={"source_id": source["source_id"]}).json()["imported"] == 5
        jazz = {track["title"]: track["track_id"] for track in client.get("/api/v1/library/tracks").json()["items"] if track["genres"] == ["Jazz"]}
        playlist_id = client.post("/api/v1/playlists", json={"name": "Evening"}).json()["playlist_id"]
        client.post(f"/api/v1/playlists/{playlist_id}/items", json={"track_id": jazz["j1"]})
        sessions = []
        for _ in range(2):  # four Likes in two sessions about at least two tracks: the long-term gate is met
            session_id = client.post("/api/v1/sessions", json={"context": {"temporary_genres": ["Jazz"]}}).json()["session"]["session_id"]
            _like_two(client, session_id)
            sessions.append(session_id)
        open_session = client.get(f"/api/v1/sessions/{sessions[-1]}").json()
        before = _everything(client, sessions, playlist_id)
    profile, adjustments = _long_term(api_settings.database_url, listener)
    assert open_session["session"]["status"] == "active" and open_session["playing"] is not None and open_session["queue"]
    assert profile is not None and profile.preferred_genres == ("Jazz",)

    second_run = create_app(api_settings, rng_factory=lambda: _NeverExplore(0))
    with TestClient(second_run) as client:
        assert second_run.state.container.listener_profile_id == listener
        after = _everything(client, sessions, playlist_id)
        ended = client.get(f"/api/v1/sessions/{sessions[-1]}").json()
        fresh = client.post("/api/v1/sessions", json={"context": {"temporary_genres": ["Jazz"]}}).json()
        listed = client.get("/api/v1/sessions").json()
        audio_status = client.get(f"/api/v1/tracks/{jazz['j1']}/audio").status_code

    assert after == before  # library, metadata, playlist, turns, and feedback, exactly
    assert _long_term(api_settings.database_url, listener) == (profile, adjustments)
    assert (ended["session"]["status"], ended["session"]["end_reason"], ended["playing"], ended["queue"]) == ("ended", "app_restarted", None, [])
    assert fresh["session"]["session_id"] not in sessions
    assert (fresh["session"]["status"], fresh["playing"], len(fresh["queue"])) == ("active", None, 3)
    assert [item["status"] for item in listed["items"]] == ["active", "ended", "ended"]
    assert audio_status == 200


_FIRST_LIBRARY_REVISION = "2540be2956b8"  # B2: listener profiles, sources, tracks, labels, source files


def test_a_database_from_the_first_library_migration_upgrades_with_its_data_and_the_app_serves_it(database_url, media_root, api_settings):
    """Rows written by the B2 schema, as B2 wrote them, through every later migration to head, then used."""
    command.upgrade(alembic_config(database_url), _FIRST_LIBRARY_REVISION)
    listener, source = "3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e", "0c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e40"
    tracks = {"5e4f4a3b-8c2d-4e0f-9a8b-7c6d5e4f4a30": ("Blue in Green", "Jazz"), "5e4f4a3b-8c2d-4e0f-9a8b-7c6d5e4f4a31": ("Drift", "Ambient")}
    at = "2026-10-19 12:00:00"
    engine = create_database_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO listener_profiles (id, is_default, created_at) VALUES (?, 1, ?)", (listener, at))
            connection.exec_driver_sql("INSERT INTO library_sources (id, path, status, created_at) VALUES (?, '/music', 'ACTIVE', ?)", (source, at))
            for number, (track_id, (title, genre)) in enumerate(tracks.items()):
                connection.exec_driver_sql(
                    "INSERT INTO tracks (id, sha256, size_bytes, audio_format, status, original_filename, title, artist, created_at, updated_at) "
                    "VALUES (?, ?, 4, 'flac', 'IMPORTED', ?, ?, ?, ?, ?)",
                    (track_id, str(number) * 64, f"{title}.flac", title, f"Artist {number}", at, at),
                )
                connection.exec_driver_sql(
                    "INSERT INTO track_labels (id, track_id, kind, value, source, is_primary) VALUES (?, ?, 'genre', ?, 'embedded_tags', 1)",
                    (f"7d1f2b3c-4d5e-4c55-9e0a-3f2c4a8e1b7{number}", track_id, genre),
                )
                connection.exec_driver_sql(
                    "INSERT INTO source_files (id, source_id, relative_path, size_bytes, modified_ns, sha256, status, track_id, created_at, updated_at) "
                    "VALUES (?, ?, ?, 4, 7, ?, 'IMPORTED', ?, ?, ?)",
                    (f"9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6{number}", source, f"{title}.flac", str(number) * 64, track_id, at, at),
                )
    finally:
        engine.dispose()
    media_root.mkdir(parents=True)
    for track_id in tracks:
        (media_root / f"{track_id}.flac").write_bytes(b"fLaC")

    app = create_app(api_settings, rng_factory=lambda: _NeverExplore(0))  # the app's startup upgrades to head
    with TestClient(app) as client:
        library = client.get("/api/v1/library/tracks").json()
        vocabulary = client.get("/api/v1/listening/vocabulary").json()
        started = client.post("/api/v1/sessions", json={"context": {"temporary_genres": ["Jazz"]}})
        assert app.state.container.listener_profile_id == listener

    assert {(track["track_id"], track["title"], tuple(track["genres"]), track["status"]) for track in library["items"]} == {
        (track_id, title, (genre,), "imported") for track_id, (title, genre) in tracks.items()
    }
    assert (vocabulary["genres"], vocabulary["library"]) == (["Ambient", "Jazz"], {"ready": True, "playable_tracks": 2})
    assert started.status_code == 201
    assert started.json()["queue"][0]["track"]["title"] == "Blue in Green"
    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM library_revision").scalar_one() == 1
    finally:
        engine.dispose()
