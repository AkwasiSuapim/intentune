"""Session routes (B8): start, read, steer, playback events, and reactions, through HTTP.

The ranking itself is Policy v1's and is tested at the application level
(test_queue_refresh.py, test_feedback_service.py). These tests check that the
routes reach it and report its results faithfully.
"""

import pytest

from src.intentune.domain.policy import POLICY_V1
from src.intentune.domain.session import LISTENER_REPLAY_ALGORITHM

_UNKNOWN = "1d6b1f4e-0c3a-4f2b-8e5d-7a9c0b1e2f3a"


def _start(client, genres=("Ambient",)):
    response = client.post("/api/v1/sessions", json={"context": {"temporary_genres": list(genres)}})
    assert response.status_code == 201
    return response.json()


def _turn(client, session_id, **body):
    return client.post(f"/api/v1/sessions/{session_id}/turns", json=body)


def _playing(client, genres=("Ambient",)):
    """A session whose first track is playing: (session_id, state after the Play turn)."""
    session_id = _start(client, genres)["session"]["session_id"]
    response = _turn(client, session_id, kind="next")
    assert response.status_code == 200
    return session_id, response.json()["state"]


def _titles(occurrences):
    return [occurrence["track"]["title"] for occurrence in occurrences]


def _error(response):
    return response.json()["error"]


# --- Start and read ------------------------------------------------------------------


def test_starting_a_session_surfaces_its_first_queue_with_the_tracks(client, library_tracks):
    state = _start(client)

    session = state["session"]
    assert (session["status"], session["ended_at"], session["end_reason"]) == ("active", None, None)
    assert session["context"]["temporary_genres"] == ["Ambient"]
    assert session["context"]["target_energy"] is None  # nothing absent is filled in
    assert state["playing"] is None
    assert sorted(_titles(state["queue"])) == ["a1", "a2", "a3"]
    first = state["queue"][0]
    assert set(first) == {
        "occurrence_id", "track", "status", "rank", "score", "algorithm", "is_exploration", "surfaced_position",
        "queue_position", "surfaced_at", "started_at", "finished_at",
    }
    assert (first["status"], first["algorithm"], first["started_at"]) == ("queued", POLICY_V1.version, None)
    assert [occurrence["queue_position"] for occurrence in state["queue"]] == [0, 1, 2]
    assert [occurrence["surfaced_position"] for occurrence in state["queue"]] == [0, 1, 2]
    assert first["track"] == library_tracks[first["track"]["title"]]


@pytest.mark.parametrize("context", [{}, {"temporary_genres": ["Ambient"]}, {"temporary_moods": ["Calm"], "target_energy": 0.5}])
def test_no_session_starts_before_the_library_has_playable_music(client, context):
    """A setup state, not an unsupported intent: music must be imported first, whatever the intent asks for."""
    response = client.post("/api/v1/sessions", json={"context": context})

    assert response.status_code == 409
    error = response.json()["error"]
    assert (error["code"], error["details"]) == ("LIBRARY_NOT_READY", {})
    assert error["message"] == "Your library has no playable music yet. Import some music to start listening."
    assert client.get("/api/v1/sessions").json()["total"] == 0


def test_the_unmapped_context_fields_are_accepted_and_stored(client, library_tracks):
    """Their mapping into Policy v1 is unfinished, so they rank nothing, but they are part of the intent and kept."""
    context = {"temporary_genres": ["Ambient"], "current_mood": "tired", "listening_goal": "focus", "activity": "reading"}

    session = _start(client, genres=())  # a session in progress first
    response = client.post("/api/v1/sessions", json={"context": context})

    assert response.status_code == 201
    stored = response.json()["session"]["context"]
    assert {key: stored[key] for key in context} == context
    assert session["session"]["session_id"] != response.json()["session"]["session_id"]


def test_starting_again_ends_the_previous_session(client, library_tracks):
    first = _start(client)["session"]["session_id"]
    _start(client, ("Jazz",))

    previous = client.get(f"/api/v1/sessions/{first}").json()["session"]

    assert (previous["status"], previous["end_reason"]) == ("ended", "replaced_by_new_session")
    assert previous["ended_at"] is not None


def test_sessions_are_listed_newest_first_and_paged(client, library_tracks):
    ids = [_start(client)["session"]["session_id"] for _ in range(3)]

    everything = client.get("/api/v1/sessions").json()
    second_page = client.get("/api/v1/sessions", params={"limit": 2, "offset": 2}).json()

    assert [session["session_id"] for session in everything["items"]] == ids[::-1]
    assert [session["status"] for session in everything["items"]] == ["active", "ended", "ended"]
    assert (second_page["total"], [session["session_id"] for session in second_page["items"]]) == (3, [ids[0]])


def test_a_session_shows_how_it_got_here(client, library_tracks):
    session_id, playing = _playing(client)
    occurrence_id = playing["playing"]["occurrence_id"]
    client.post(f"/api/v1/sessions/{session_id}/recommendations/{occurrence_id}/reactions", json={"reaction": "like"})

    detail = client.get(f"/api/v1/sessions/{session_id}").json()

    assert [turn["kind"] for turn in detail["turns"]] == ["initial_intent", "next"]
    assert [turn["sequence"] for turn in detail["turns"]] == [1, 2]
    assert detail["turns"][1]["occurrence_id"] is None  # Play: nothing was playing yet
    assert detail["playing"]["occurrence_id"] == occurrence_id
    assert [event["event_type"] for event in detail["feedback_events"]] == ["like"]
    statuses = [occurrence["status"] for occurrence in detail["occurrences"]]
    assert statuses.count("playing") == 1 and statuses.count("queued") == len(detail["queue"])
    assert {"replaced"} == set(statuses) - {"playing", "queued"}  # each refresh replaced the queue before it


def test_an_unknown_session_is_not_found(client):
    for response in (
        client.get(f"/api/v1/sessions/{_UNKNOWN}"),
        _turn(client, _UNKNOWN, kind="next"),
        client.post(f"/api/v1/sessions/{_UNKNOWN}/recommendations/{_UNKNOWN}/reactions", json={"reaction": "like"}),
    ):
        assert response.status_code == 404
        assert _error(response)["code"] == "SESSION_NOT_FOUND"


# --- Turns -----------------------------------------------------------------------------


def test_next_while_nothing_plays_starts_the_first_queued_track(client, library_tracks):
    started = _start(client)

    response = _turn(client, started["session"]["session_id"], kind="next")

    assert response.status_code == 200
    body = response.json()
    assert (body["turn"]["kind"], body["turn"]["sequence"]) == ("next", 2)
    assert body["state"]["playing"]["occurrence_id"] == started["queue"][0]["occurrence_id"]
    assert body["state"]["playing"]["status"] == "playing"
    assert body["state"]["playing"]["started_at"] is not None
    assert body["state"]["playing"]["track"]["title"] not in _titles(body["state"]["queue"])


def test_next_moves_on_to_another_track(client, library_tracks):
    session_id, playing = _playing(client)

    after = _turn(client, session_id, kind="next", occurrence_id=playing["playing"]["occurrence_id"]).json()

    assert after["state"]["playing"]["occurrence_id"] != playing["playing"]["occurrence_id"]
    assert after["turn"]["occurrence_id"] == playing["playing"]["occurrence_id"]


def test_refine_replaces_the_context_and_re_ranks(client, library_tracks):
    session_id = _start(client)["session"]["session_id"]

    body = _turn(client, session_id, kind="refine", context={"temporary_genres": ["Jazz"]}).json()

    assert body["turn"]["context"]["temporary_genres"] == ["Jazz"]
    assert body["state"]["session"]["context"]["temporary_genres"] == ["Jazz"]
    assert sorted(_titles(body["state"]["queue"])) == ["j1", "j2", "j3"]


@pytest.mark.parametrize(
    "context, unavailable",
    [
        ({"temporary_genres": ["Ambient"], "temporary_moods": ["Calm"]}, ["mood"]),
        ({"temporary_genres": ["Ambient"], "desired_mood": "Calm"}, ["mood"]),
        ({"temporary_genres": ["Ambient"], "target_energy": 0.3}, ["energy"]),
        ({"temporary_genres": ["Polka"]}, ["genre"]),
        ({"temporary_genres": ["Jazz"], "target_energy": 0.3}, ["energy"]),
        ({"temporary_genres": ["Ambient"], "target_valence": 0.6, "target_tempo_bpm": 120}, ["tempo", "valence"]),
    ],
    ids=["mood", "desired-mood", "energy", "undeclared-genre", "usable-genre-with-energy", "measured-targets"],
)
def test_a_structured_refine_the_library_cannot_use_is_refused_and_changes_nothing(client, library_tracks, context, unavailable):
    """The library declares Ambient and Jazz, no moods, and no energy. Nothing of the refinement is applied, not even its usable part."""
    session_id = _start(client)["session"]["session_id"]
    _turn(client, session_id, kind="next")
    before = client.get(f"/api/v1/sessions/{session_id}").json()

    response = _turn(client, session_id, kind="refine", context=context)

    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], error["details"]) == ("INTENT_UNAVAILABLE", {"unavailable": unavailable, "dimensions": ["genre"]})
    assert client.get(f"/api/v1/sessions/{session_id}").json() == before  # no turn, no context change, no new queue


def test_a_structured_start_the_library_cannot_use_starts_nothing(client, library_tracks):
    """The Focus starter's intent (Focused, Medium energy) over a library with genres only."""
    playing_on = _start(client)["session"]["session_id"]

    response = client.post("/api/v1/sessions", json={"context": {"temporary_moods": ["Focused"], "target_energy": 0.5}})

    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], error["details"]) == ("INTENT_UNAVAILABLE", {"unavailable": ["mood", "energy"], "dimensions": ["genre"]})
    assert error["message"] == "Your library doesn't describe that mood or energy yet, so that can't change what plays. Try a genre."
    sessions = client.get("/api/v1/sessions").json()
    assert [(session["session_id"], session["status"]) for session in sessions["items"]] == [(playing_on, "active")]


def test_not_for_me_about_the_playing_track_moves_on_and_keeps_it_out(client, library_tracks):
    session_id, playing = _playing(client)
    rejected = playing["playing"]

    body = _turn(client, session_id, kind="not_for_me").json()

    assert body["turn"]["occurrence_id"] == rejected["occurrence_id"]
    assert body["state"]["playing"]["track"]["track_id"] != rejected["track"]["track_id"]
    assert rejected["track"]["track_id"] not in [occurrence["track"]["track_id"] for occurrence in body["state"]["queue"]]


@pytest.mark.parametrize("kind", ["surprise_me", "more_familiar", "try_something_different"])
def test_controls_are_turns_without_a_target(client, library_tracks, kind):
    session_id = _start(client)["session"]["session_id"]

    accepted = _turn(client, session_id, kind=kind)
    refused = _turn(client, session_id, kind=kind, occurrence_id=_UNKNOWN)

    assert accepted.status_code == 200
    assert accepted.json()["turn"]["kind"] == kind
    assert refused.status_code == 422
    assert _error(refused)["message"] == f"A {kind.upper()} turn is not about a single recommendation."


def test_the_initial_intent_cannot_be_sent_as_a_turn(client, library_tracks):
    session_id = _start(client)["session"]["session_id"]

    response = _turn(client, session_id, kind="initial_intent")

    assert response.status_code == 409
    error = _error(response)
    assert (error["code"], error["message"]) == ("INVALID_SESSION_TRANSITION", "A session's initial intent is set when the session starts.")


def test_a_turn_about_an_unknown_recommendation_is_not_found(client, library_tracks):
    session_id = _start(client)["session"]["session_id"]

    response = _turn(client, session_id, kind="more_like_this", occurrence_id=_UNKNOWN)

    assert response.status_code == 404
    assert _error(response)["code"] == "RECOMMENDATION_NOT_FOUND"


def test_a_turn_with_nothing_to_apply_to_is_an_invalid_transition(client, library_tracks):
    session_id = _start(client)["session"]["session_id"]

    response = _turn(client, session_id, kind="not_for_me")

    assert response.status_code == 409
    assert _error(response)["code"] == "INVALID_SESSION_TRANSITION"


@pytest.mark.parametrize(
    "body",
    [{"kind": "louder"}, {}, {"kind": "next", "text": "play something calm"}, {"kind": "NEXT"}, {"kind": "next", "context": {}}],
    ids=["unknown-kind", "no-kind", "raw-text", "uppercase", "context-on-next"],
)
def test_turn_bodies_are_validated(client, library_tracks, body):
    session_id = _start(client)["session"]["session_id"]

    response = _turn(client, session_id, **body)

    assert response.status_code == 422
    assert _error(response)["code"] == "VALIDATION_ERROR"


def test_an_ended_session_takes_no_more_commands(client, library_tracks):
    old_id, playing = _playing(client)
    _start(client)

    responses = (
        _turn(client, old_id, kind="next"),
        client.post(
            f"/api/v1/sessions/{old_id}/recommendations/{playing['playing']['occurrence_id']}/reactions", json={"reaction": "like"}
        ),
    )

    for response in responses:
        assert response.status_code == 409
        error = _error(response)
        assert (error["code"], error["message"]) == ("INVALID_SESSION_TRANSITION", "The session has ended. Start a new session to keep listening.")


# --- Playback events -------------------------------------------------------------------


def test_an_early_skip_is_stored_as_a_raw_fact_and_moves_on(client, library_tracks):
    session_id, playing = _playing(client)
    skipped = playing["playing"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/playback-events",
        json={"occurrence_id": skipped["occurrence_id"], "event_type": "skip", "played_seconds": 20, "duration_seconds": 200},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["event"]["event_type"] == "skip"
    assert (body["event"]["played_seconds"], body["event"]["duration_seconds"], body["event"]["played_fraction"]) == (20.0, 200.0, 0.1)
    assert body["event_weight"] == -0.5
    assert (body["interpretation"]["weight"], body["interpretation"]["basis"], body["interpretation"]["excluded"]) == (-0.5, "passive", False)
    assert body["interpretation"]["occurrence_id"] == skipped["occurrence_id"]
    assert body["state"]["playing"]["occurrence_id"] != skipped["occurrence_id"]


def test_a_completed_track_is_positive_evidence(client, library_tracks):
    session_id, playing = _playing(client)

    body = client.post(
        f"/api/v1/sessions/{session_id}/playback-events",
        json={"occurrence_id": playing["playing"]["occurrence_id"], "event_type": "complete", "played_seconds": 200, "duration_seconds": 200},
    ).json()

    assert body["event_weight"] == POLICY_V1.full_play_weight
    assert body["interpretation"]["basis"] == "passive"


def test_a_skip_of_a_track_that_never_played_is_an_invalid_transition(client, library_tracks):
    state = _start(client)

    response = client.post(
        f"/api/v1/sessions/{state['session']['session_id']}/playback-events",
        json={"occurrence_id": state["queue"][0]["occurrence_id"], "event_type": "skip", "played_seconds": 1, "duration_seconds": 10},
    )

    assert response.status_code == 409
    assert _error(response)["code"] == "INVALID_SESSION_TRANSITION"


@pytest.mark.parametrize(
    "change",
    [
        {"played_seconds": -1},
        {"duration_seconds": 0},
        {"played_seconds": "12"},
        {"duration_seconds": None},
        {"event_type": "like"},
        {"event_type": "playlist_add"},
        {"position_seconds": 3},
    ],
    ids=["negative-played", "zero-duration", "text-seconds", "no-duration", "reaction-type", "playlist-add", "progress-tick"],
)
def test_playback_event_bodies_are_validated(client, library_tracks, change):
    session_id, playing = _playing(client)
    body = {"occurrence_id": playing["playing"]["occurrence_id"], "event_type": "skip", "played_seconds": 12, "duration_seconds": 200}

    response = client.post(f"/api/v1/sessions/{session_id}/playback-events", json={**body, **change})

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert [problem["location"] for problem in error["details"]["errors"]] == [["body", next(iter(change))]]  # the schema refused it


# --- Reactions ---------------------------------------------------------------------------


def test_a_like_is_explicit_positive_evidence_and_leaves_playback_alone(client, library_tracks):
    session_id, playing = _playing(client)
    occurrence_id = playing["playing"]["occurrence_id"]

    response = client.post(f"/api/v1/sessions/{session_id}/recommendations/{occurrence_id}/reactions", json={"reaction": "like"})

    assert response.status_code == 201
    body = response.json()
    assert (body["event"]["event_type"], body["event"]["played_seconds"], body["event_weight"]) == ("like", None, 1.0)
    assert (body["interpretation"]["weight"], body["interpretation"]["basis"]) == (1.0, "explicit")
    assert body["state"]["playing"]["occurrence_id"] == occurrence_id


def test_an_unlike_takes_a_like_back_and_both_stay_in_the_history(client, library_tracks):
    session_id, playing = _playing(client)
    occurrence_id = playing["playing"]["occurrence_id"]
    reactions = f"/api/v1/sessions/{session_id}/recommendations/{occurrence_id}/reactions"
    client.post(reactions, json={"reaction": "like"})

    response = client.post(reactions, json={"reaction": "unlike"})

    assert response.status_code == 201
    body = response.json()
    assert (body["event"]["event_type"], body["event_weight"]) == ("unlike", 0.0)
    assert (body["interpretation"]["weight"], body["interpretation"]["basis"], body["interpretation"]["excluded"]) == (0.0, "none", False)
    assert body["state"]["playing"]["occurrence_id"] == occurrence_id
    events = client.get(f"/api/v1/sessions/{session_id}").json()["feedback_events"]
    assert [event["event_type"] for event in events] == ["like", "unlike"]


def test_not_for_me_as_a_reaction_excludes_the_track_and_moves_on(client, library_tracks):
    session_id, playing = _playing(client)
    occurrence_id = playing["playing"]["occurrence_id"]

    body = client.post(
        f"/api/v1/sessions/{session_id}/recommendations/{occurrence_id}/reactions", json={"reaction": "not_for_me"}
    ).json()

    assert (body["interpretation"]["weight"], body["interpretation"]["excluded"]) == (-1.0, True)
    assert body["state"]["playing"]["occurrence_id"] != occurrence_id


def test_replay_of_a_past_track_plays_it_again_as_the_listeners_choice(client, library_tracks):
    session_id, playing = _playing(client)
    first = playing["playing"]
    _turn(client, session_id, kind="next")

    body = client.post(
        f"/api/v1/sessions/{session_id}/recommendations/{first['occurrence_id']}/reactions", json={"reaction": "replay"}
    ).json()

    now_playing = body["state"]["playing"]
    assert now_playing["track"]["track_id"] == first["track"]["track_id"]
    assert now_playing["occurrence_id"] != first["occurrence_id"]
    assert (now_playing["algorithm"], now_playing["score"]) == (LISTENER_REPLAY_ALGORITHM, None)


def test_a_reaction_to_a_recommendation_of_another_session_is_not_found(client, library_tracks):
    _, old = _playing(client)
    session_id = _start(client)["session"]["session_id"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/recommendations/{old['playing']['occurrence_id']}/reactions", json={"reaction": "like"}
    )

    assert response.status_code == 404
    assert _error(response)["code"] == "RECOMMENDATION_NOT_FOUND"


@pytest.mark.parametrize("body", [{"reaction": "playlist_add"}, {"reaction": "skip"}, {"reaction": "love"}, {}])
def test_reaction_bodies_are_validated(client, library_tracks, body):
    session_id, playing = _playing(client)

    response = client.post(f"/api/v1/sessions/{session_id}/recommendations/{playing['playing']['occurrence_id']}/reactions", json=body)

    assert response.status_code == 422
    assert [problem["location"] for problem in _error(response)["details"]["errors"]] == [["body", "reaction"]]  # the schema refused it
