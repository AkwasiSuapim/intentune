"""The API's error envelope, request IDs, validation, and CORS (B8, spec §26)."""

import re

import pytest

from src.intentune.api import views
from src.intentune.api.schemas import TrackOut

_GENERATED_ID = re.compile(r"^[0-9a-f]{32}$")


def _error(response):
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details", "request_id"}
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
    return body["error"]


# --- Request IDs ---------------------------------------------------------------------


def test_every_response_carries_a_generated_request_id(client):
    first = client.get("/health")
    second = client.get("/health")

    assert first.status_code == 200
    assert _GENERATED_ID.match(first.headers["X-Request-ID"])
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


def test_a_safe_client_request_id_is_kept_in_the_header_and_the_error(client):
    response = client.get("/api/v1/sessions/unknown", headers={"X-Request-ID": "web-42.a_b"})

    assert response.headers["X-Request-ID"] == "web-42.a_b"
    assert _error(response)["request_id"] == "web-42.a_b"


@pytest.mark.parametrize("unsafe", [b"has space", b"x" * 65, b"semi;colon", "\u00e9t\u00e9".encode("utf-8"), b""])
def test_an_unsafe_client_request_id_is_replaced(client, unsafe):
    response = client.get("/health", headers={"X-Request-ID": unsafe})

    assert _GENERATED_ID.match(response.headers["X-Request-ID"])


# --- The envelope --------------------------------------------------------------------


def test_a_missing_resource_answers_with_its_code_and_a_fixed_message(client):
    response = client.get("/api/v1/sessions/0b5f1a52-4d1b-4a8e-9a39-0e0c4a1d2f3b")

    assert response.status_code == 404
    error = _error(response)
    assert error["code"] == "SESSION_NOT_FOUND"
    assert error["message"] == "The session does not exist."
    assert error["details"] == {}
    assert "0b5f1a52" not in error["message"]


def test_an_unknown_route_answers_not_found_in_the_envelope(client):
    response = client.get("/api/v1/nothing-here")

    assert response.status_code == 404
    assert _error(response)["code"] == "NOT_FOUND"


def test_a_wrong_method_answers_method_not_allowed_with_the_allowed_methods(client):
    response = client.delete("/health")

    assert response.status_code == 405
    assert _error(response)["code"] == "METHOD_NOT_ALLOWED"
    assert response.headers["allow"] == "GET"


# --- Validation ----------------------------------------------------------------------


def test_a_schema_violation_lists_where_the_problems_are(client):
    response = client.post("/api/v1/sessions", json={"context": {"target_energy": 1.5, "mood": "calm"}})

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "VALIDATION_ERROR"
    problems = {tuple(problem["location"]): problem["type"] for problem in error["details"]["errors"]}
    assert problems == {("body", "context", "target_energy"): "less_than_equal", ("body", "context", "mood"): "extra_forbidden"}
    assert all("input" not in problem for problem in error["details"]["errors"])  # the client's values are not echoed


def test_a_body_that_is_not_json_is_a_bad_request(client):
    response = client.post("/api/v1/sessions", content=b"{not json", headers={"Content-Type": "application/json"})

    assert response.status_code == 400
    error = _error(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "The request body is not valid JSON."


@pytest.mark.parametrize(
    "context",
    [
        {"target_energy": "0.5"},
        {"target_energy": True},
        {"target_tempo_bpm": 0},
        {"target_tempo_bpm": -120},
        {"temporary_genres": ["   "]},
        {"temporary_genres": ["x" * 101]},
        {"temporary_genres": [f"genre {index}" for index in range(21)]},
        {"activity": "y" * 101},
        {"current_mood": 7},
    ],
    ids=["number-as-text", "boolean", "zero-tempo", "negative-tempo", "blank-label", "long-label", "too-many-labels", "long-text", "number-as-label"],
)
def test_context_values_are_checked_strictly(client, context):
    response = client.post("/api/v1/sessions", json={"context": context})

    assert response.status_code == 422
    assert _error(response)["code"] == "VALIDATION_ERROR"


def test_the_applications_own_checks_answer_as_validation_errors(client, library_tracks):
    session_id = client.post("/api/v1/sessions", json={"context": {}}).json()["session"]["session_id"]

    response = client.post(f"/api/v1/sessions/{session_id}/turns", json={"kind": "refine"})

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "A REFINE turn carries the new context, and only a REFINE turn does."


# --- Unexpected errors ----------------------------------------------------------------


def test_an_unexpected_error_is_logged_and_answered_without_its_details(client, monkeypatch, caplog):
    class Broken:
        def list_sessions(self, listener_profile_id):
            raise RuntimeError(r"boom in C:\Users\someone\secret\intentune.db")

    monkeypatch.setattr(client.app.state.container, "sessions", lambda: Broken())

    response = client.get("/api/v1/sessions", headers={"X-Request-ID": "trace-me"})

    assert response.status_code == 500
    error = _error(response)
    assert error == {"code": "INTERNAL_ERROR", "message": "Something went wrong. Please try again.", "details": {}, "request_id": "trace-me"}
    assert "secret" not in response.text and "Traceback" not in response.text
    assert "Unexpected error (request trace-me)" in caplog.text
    assert "boom in" in caplog.text  # the details stay in the server log


def test_a_response_that_cannot_be_built_is_a_server_error_not_a_validation_error(client, monkeypatch, library_tracks):
    def broken_track_out(track):
        return TrackOut.model_validate({"track_id": track.track_id})

    monkeypatch.setattr(views, "track_out", broken_track_out)

    response = client.get("/api/v1/library/tracks")

    assert response.status_code == 500
    assert _error(response)["code"] == "INTERNAL_ERROR"
    assert "track_id" not in response.text


# --- CORS ----------------------------------------------------------------------------


def test_the_frontend_origin_may_read_responses_and_their_request_ids(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    exposed = {name.strip().lower() for name in response.headers["access-control-expose-headers"].split(",")}
    assert {"x-request-id", "content-range", "accept-ranges"} <= exposed


def test_error_responses_carry_cors_headers_too(client):
    response = client.get("/api/v1/playlists/unknown", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 404
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_an_unexpected_error_carries_cors_headers_so_the_frontend_can_read_it(client, monkeypatch):
    class Broken:
        def list_playlists(self, listener_profile_id):
            raise RuntimeError("boom")

    monkeypatch.setattr(client.app.state.container, "playlists", lambda: Broken())

    response = client.get("/api/v1/playlists", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert _error(response)["code"] == "INTERNAL_ERROR"


def test_a_preflight_from_the_frontend_origin_is_allowed(client):
    response = client.options(
        "/api/v1/playlists/some-id",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_other_origins_are_not_allowed(client):
    response = client.get("/health", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers
