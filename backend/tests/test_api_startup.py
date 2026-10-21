"""Backend startup and shutdown, settings, and the entry point (B8)."""

import dataclasses
import time
from pathlib import Path

import pytest
from sqlalchemy import inspect
from starlette.testclient import TestClient

from src.intentune.adapters.managed_media import DEFAULT_MEDIA_ROOT
from src.intentune.api import __main__ as entry_point
from src.intentune.api.app import create_app
from src.intentune.api.container import Container
from src.intentune.api.settings import ApiSettings
from src.intentune.persistence.db import BACKEND_ROOT, DEFAULT_DATABASE_PATH, create_database_engine


def _wait_for(condition, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


# --- Startup and shutdown ----------------------------------------------------------------


def test_startup_migrates_a_fresh_database(client, api_settings):
    engine = create_database_engine(api_settings.database_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert {"alembic_version", "listener_profiles", "tracks", "listening_sessions", "playlists"} <= tables


def test_the_local_listener_is_created_once_and_kept_across_restarts(api_settings):
    first = create_app(api_settings)
    with TestClient(first):
        listener = first.state.container.listener_profile_id
    again = create_app(api_settings)
    with TestClient(again):
        assert again.state.container.listener_profile_id == listener


def test_sessions_left_active_by_a_previous_run_end_at_startup(api_settings, music, audio):
    audio.wav(music / "one.wav", seed=1, genre="Jazz")
    audio.wav(music / "two.wav", seed=2, genre="Jazz")
    with TestClient(create_app(api_settings)) as before:
        source = before.post("/api/v1/library/sources", json={"path": str(music)}).json()
        before.post("/api/v1/library/import", json={"source_id": source["source_id"]})
        session_id = before.post("/api/v1/sessions", json={"context": {"temporary_genres": ["Jazz"]}}).json()["session"]["session_id"]

    with TestClient(create_app(api_settings)) as after:
        detail = after.get(f"/api/v1/sessions/{session_id}").json()

    assert (detail["session"]["status"], detail["session"]["end_reason"]) == ("ended", "app_restarted")
    assert (detail["playing"], detail["queue"]) == (None, [])
    assert {occurrence["status"] for occurrence in detail["occurrences"]} == {"discarded"}


def test_the_analysis_worker_runs_while_the_app_serves_and_analyzes_imported_tracks(api_settings, music, audio):
    settings = dataclasses.replace(api_settings, start_worker=True, analysis_idle_seconds=0.05)
    audio.tone(music / "tone.wav", seconds=0.5)
    app = create_app(settings)
    with TestClient(app) as client:
        worker = app.state.container.worker
        assert worker.is_running
        source = client.post("/api/v1/library/sources", json={"path": str(music)}).json()
        client.post("/api/v1/library/import", json={"source_id": source["source_id"]})

        assert _wait_for(lambda: client.get("/api/v1/library/tracks").json()["items"][0]["status"] == "ready")
        [job] = client.get("/api/v1/library/jobs").json()["items"]
        assert (job["status"], job["failure_reason"]) == ("succeeded", None)

    assert not worker.is_running


def test_the_startup_scan_imports_in_the_background(api_settings, music, audio):
    with TestClient(create_app(api_settings)) as before:
        before.post("/api/v1/library/sources", json={"path": str(music)})
    audio.wav(music / "added-while-closed.wav", seed=3, title="Added", genre="Jazz")

    app = create_app(dataclasses.replace(api_settings, startup_scan=True))
    with TestClient(app) as client:
        assert app.state.container.scans.wait(timeout=15)
        titles = [track["title"] for track in client.get("/api/v1/library/tracks").json()["items"]]

    assert titles == ["Added"]


def test_without_the_startup_scan_nothing_is_imported_at_startup(api_settings, music, audio):
    with TestClient(create_app(api_settings)) as before:
        before.post("/api/v1/library/sources", json={"path": str(music)})
    audio.wav(music / "one.wav", seed=1)

    app = create_app(api_settings)
    with TestClient(app) as client:
        assert app.state.container.scans.wait(timeout=15)  # a scan, had one started, has ended
        assert client.get("/api/v1/library/tracks").json()["total"] == 0


def test_the_listener_is_unknown_before_startup(api_settings):
    container = Container(api_settings)

    with pytest.raises(RuntimeError, match="has not started"):
        container.listener_profile_id
    container.stop()


def test_a_failed_startup_stops_what_it_started(api_settings, monkeypatch):
    app = create_app(dataclasses.replace(api_settings, start_worker=True))
    container = app.state.container
    stopped = []
    real_stop = container.stop

    def failing_end(self):
        raise RuntimeError("cannot end sessions")

    monkeypatch.setattr("src.intentune.application.sessions.SessionService.end_sessions_from_previous_run", failing_end)
    monkeypatch.setattr(container, "stop", lambda: (stopped.append(True), real_stop()))

    with pytest.raises(RuntimeError, match="cannot end sessions"):
        with TestClient(app):
            pass

    assert stopped == [True]
    assert not container.worker.is_running


# --- Settings -----------------------------------------------------------------------------


def test_settings_default_to_the_backend_data_folder_and_the_vite_origin():
    settings = ApiSettings.from_environment({})

    assert Path(settings.database_url.database) == DEFAULT_DATABASE_PATH
    assert settings.media_root == DEFAULT_MEDIA_ROOT
    assert settings.cors_origins == ("http://localhost:5173",)
    assert (settings.host, settings.port) == ("127.0.0.1", 8000)
    assert settings.start_worker and settings.startup_scan


def test_relative_paths_are_resolved_against_the_backend_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # not against the working directory

    settings = ApiSettings.from_environment({"DATABASE_URL": "sqlite:///./elsewhere/test.db", "MEDIA_ROOT": "./elsewhere/media"})

    assert Path(settings.database_url.database) == BACKEND_ROOT / "elsewhere" / "test.db"
    assert settings.media_root == BACKEND_ROOT / "elsewhere" / "media"


def test_an_absolute_media_root_is_kept(tmp_path):
    assert ApiSettings.from_environment({"MEDIA_ROOT": str(tmp_path)}).media_root == tmp_path


@pytest.mark.parametrize(
    "raw, origins",
    [(" http://a.test , http://b.test ,", ("http://a.test", "http://b.test")), ("", ()), ("http://a.test", ("http://a.test",))],
)
def test_cors_origins_are_a_comma_separated_list(raw, origins):
    assert ApiSettings.from_environment({"CORS_ORIGINS": raw}).cors_origins == origins


def test_host_and_port_come_from_the_environment():
    settings = ApiSettings.from_environment({"API_HOST": "0.0.0.0", "API_PORT": "9001"})

    assert (settings.host, settings.port) == ("0.0.0.0", 9001)


@pytest.mark.parametrize("port", ["eighty", "0", "65536", "-1"])
def test_a_bad_port_is_refused(port):
    with pytest.raises(ValueError, match="API_PORT"):
        ApiSettings.from_environment({"API_PORT": port})


def test_a_non_sqlite_database_is_refused():
    with pytest.raises(ValueError, match="only SQLite"):
        ApiSettings.from_environment({"DATABASE_URL": "postgresql://localhost/intentune"})


def test_a_dot_env_file_is_not_loaded(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("DATABASE_URL=sqlite:///./from-dot-env.db\nAPI_PORT=1234\n")
    monkeypatch.chdir(tmp_path)
    for name in ("DATABASE_URL", "MEDIA_ROOT", "CORS_ORIGINS", "API_HOST", "API_PORT"):
        monkeypatch.delenv(name, raising=False)

    settings = ApiSettings.from_environment()

    assert Path(settings.database_url.database) == DEFAULT_DATABASE_PATH
    assert settings.port == 8000


def test_create_app_reads_the_process_environment_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'env.db').as_posix()}")
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))

    app = create_app()

    assert Path(app.state.container.settings.database_url.database) == tmp_path / "env.db"
    assert app.state.container.settings.media_root == tmp_path / "media"
    app.state.container.stop()


# --- Entry point ----------------------------------------------------------------------------


def test_the_entry_point_serves_the_app_on_the_configured_host_and_port(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'main.db').as_posix()}")
    monkeypatch.setenv("API_HOST", "127.0.0.2")
    monkeypatch.setenv("API_PORT", "8123")
    monkeypatch.setattr(entry_point.uvicorn, "run", lambda app, host, port: calls.append((app, host, port)))
    monkeypatch.setattr(entry_point.logging, "basicConfig", lambda **kwargs: None)

    entry_point.main()

    [(app, host, port)] = calls
    assert (host, port) == ("127.0.0.2", 8123)
    assert Path(app.state.container.settings.database_url.database) == tmp_path / "main.db"
    app.state.container.stop()
