"""Typed messages, Next with the player's facts, and the vocabulary, through HTTP (B9)."""

import uuid
from datetime import datetime, timezone

import pytest

from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork


def _start(client, **body):
    return client.post("/api/v1/sessions", json=body)


def _turn(client, session_id, **body):
    return client.post(f"/api/v1/sessions/{session_id}/turns", json=body)


def _playing(client):
    session_id = _start(client, context={"temporary_genres": ["Ambient"]}).json()["session"]["session_id"]
    state = _turn(client, session_id, kind="next").json()["state"]
    return session_id, state


def _error(response):
    return response.json()["error"]


# --- Starting -------------------------------------------------------------------------------------


def test_a_session_starts_from_words_that_refine(client, library_tracks):
    response = _start(client, message="something ambient")

    assert response.status_code == 201
    body = response.json()
    assert body["meaning"] == {"kind": "refine", "turn": None, "reaction": None}
    assert body["turn"] is None
    assert body["session"]["context"]["temporary_genres"] == ["Ambient"]
    assert sorted(occurrence["track"]["title"] for occurrence in body["queue"]) == ["a1", "a2", "a3"]


def test_a_session_starts_from_a_control(client, library_tracks):
    body = _start(client, message="Surprise me").json()

    assert body["meaning"] == {"kind": "turn", "turn": "surprise_me", "reaction": None}
    assert body["turn"]["kind"] == "surprise_me"


def test_a_session_started_from_a_context_reports_no_meaning(client, library_tracks):
    body = _start(client, context={"temporary_genres": ["Jazz"]}).json()

    assert (body["meaning"], body["turn"]) == (None, None)


@pytest.mark.parametrize("body", [{}, {"context": {}, "message": "jazz"}, {"message": ""}, {"message": "x" * 501}])
def test_a_start_takes_exactly_one_context_or_message(client, body):
    response = _start(client, **body)

    assert response.status_code == 422
    assert _error(response)["code"] == "VALIDATION_ERROR"


def test_words_that_cannot_start_a_session_are_not_understood_and_start_nothing(client, library_tracks):
    response = _start(client, message="music for driving through Accra at 2am")

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "MESSAGE_NOT_UNDERSTOOD"
    # The guidance names only what this library can use: its tracks declare genres, but no moods or energy.
    assert error["message"] == "Intentune can't act on that yet. Try a genre."
    assert error["details"] == {"reason": "unrecognized", "dimensions": ["genre"]}
    assert "Accra" not in response.text  # the words are not echoed
    assert client.get("/api/v1/sessions").json()["total"] == 0


@pytest.mark.parametrize(
    "text, reason",
    [("like this", "no_recommendation"), ("calmer but more energetic", "ambiguous"), ("no jazz", "unsupported")],
)
def test_each_reason_for_not_understanding_is_reported(client, library_tracks, text, reason):
    error = _error(_start(client, message=text))

    assert (error["code"], error["details"]["reason"]) == ("MESSAGE_NOT_UNDERSTOOD", reason)


# --- In a session ---------------------------------------------------------------------------------


def test_a_message_that_refines_answers_its_meaning_and_the_refine_turn(client, library_tracks):
    session_id, state = _playing(client)

    response = _turn(client, session_id, kind="message", text="more jazz")

    assert response.status_code == 200
    body = response.json()
    assert body["meaning"]["kind"] == "refine"
    assert body["turn"]["kind"] == "refine"
    assert body["feedback"] is None
    assert body["state"]["session"]["context"]["temporary_genres"] == ["Jazz"]
    assert body["state"]["playing"]["occurrence_id"] == state["playing"]["occurrence_id"]


def test_a_typed_reaction_answers_the_feedback_it_recorded(client, library_tracks):
    session_id, state = _playing(client)

    body = _turn(client, session_id, kind="message", text="love this", occurrence_id=state["playing"]["occurrence_id"]).json()

    assert body["meaning"] == {"kind": "reaction", "turn": None, "reaction": "like"}
    assert body["turn"] is None
    assert (body["feedback"]["event"]["event_type"], body["feedback"]["event_weight"]) == ("like", 1.0)
    assert body["feedback"]["interpretation"]["basis"] == "explicit"


def test_typed_save_asks_where_and_records_nothing(client, library_tracks):
    session_id, _ = _playing(client)
    before = client.get(f"/api/v1/sessions/{session_id}").json()

    body = _turn(client, session_id, kind="message", text="save this").json()

    assert body["meaning"]["kind"] == "save_requested"
    assert (body["turn"], body["feedback"]) == (None, None)
    after = client.get(f"/api/v1/sessions/{session_id}").json()
    assert (after["turns"], after["feedback_events"]) == (before["turns"], before["feedback_events"])


def test_typed_next_records_the_players_facts_as_a_skip(client, library_tracks):
    session_id, state = _playing(client)
    playing = state["playing"]["occurrence_id"]

    body = _turn(
        client, session_id, kind="message", text="next", occurrence_id=playing, playback={"played_seconds": 20, "duration_seconds": 200}
    ).json()

    assert (body["meaning"]["turn"], body["turn"]["kind"]) == ("next", "next")
    assert body["state"]["playing"]["occurrence_id"] != playing
    [skip] = client.get(f"/api/v1/sessions/{session_id}").json()["feedback_events"]
    assert (skip["event_type"], skip["occurrence_id"], skip["played_fraction"]) == ("skip", playing, 0.1)


def test_a_message_that_cannot_be_acted_on_changes_nothing(client, library_tracks):
    session_id, _ = _playing(client)
    before = client.get(f"/api/v1/sessions/{session_id}").json()

    response = _turn(client, session_id, kind="message", text="the weather is nice")

    assert response.status_code == 422
    assert _error(response)["code"] == "MESSAGE_NOT_UNDERSTOOD"
    assert client.get(f"/api/v1/sessions/{session_id}").json() == before


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "message"},
        {"kind": "message", "text": "   "},
        {"kind": "message", "text": "y" * 501},
        {"kind": "next", "text": "next"},
        {"kind": "surprise_me", "playback": {"played_seconds": 1, "duration_seconds": 2}},
        {"kind": "next", "playback": {"played_seconds": -1, "duration_seconds": 2}},
        {"kind": "next", "playback": {"played_seconds": 1, "duration_seconds": 0}},
    ],
    ids=["no-text", "blank-text", "long-text", "text-on-next", "playback-on-a-control", "negative-played", "zero-duration"],
)
def test_message_and_playback_fields_are_validated(client, library_tracks, body):
    session_id, _ = _playing(client)

    response = _turn(client, session_id, **body)

    assert response.status_code == 422
    assert _error(response)["code"] == "VALIDATION_ERROR"


# --- The clicked Next with the player's facts -------------------------------------------------------


def test_the_clicked_next_with_the_players_facts_records_the_skip(client, library_tracks):
    session_id, state = _playing(client)
    playing = state["playing"]["occurrence_id"]

    body = _turn(client, session_id, kind="next", occurrence_id=playing, playback={"played_seconds": 150, "duration_seconds": 200}).json()

    assert body["turn"]["occurrence_id"] == playing
    [skip] = client.get(f"/api/v1/sessions/{session_id}").json()["feedback_events"]
    assert (skip["event_type"], skip["played_seconds"], skip["duration_seconds"]) == ("skip", 150.0, 200.0)


@pytest.mark.parametrize("body", [{"kind": "next"}, {"kind": "message", "text": "next"}], ids=["clicked", "typed"])
def test_one_next_with_the_players_facts_surfaces_exactly_one_new_queue(client, library_tracks, body):
    """A second refresh would surface a queue and then replace it; one Next surfaces only the queue it answers with."""
    session_id, state = _playing(client)
    playing = state["playing"]["occurrence_id"]
    surfaced_before = {occurrence["occurrence_id"] for occurrence in client.get(f"/api/v1/sessions/{session_id}").json()["occurrences"]}

    answer = _turn(client, session_id, occurrence_id=playing, playback={"played_seconds": 30, "duration_seconds": 200}, **body).json()

    detail = client.get(f"/api/v1/sessions/{session_id}").json()
    surfaced_now = {occurrence["occurrence_id"] for occurrence in detail["occurrences"]} - surfaced_before
    queue = {occurrence["occurrence_id"] for occurrence in answer["state"]["queue"]}
    assert queue and surfaced_now == queue
    assert not any(occurrence["status"] == "replaced" and occurrence["occurrence_id"] in surfaced_now for occurrence in detail["occurrences"])
    [skip] = detail["feedback_events"]
    assert (skip["event_type"], skip["occurrence_id"]) == ("skip", playing)


def test_play_with_nothing_playing_records_no_skip(client, library_tracks):
    session_id = _start(client, context={}).json()["session"]["session_id"]

    _turn(client, session_id, kind="next", playback={"played_seconds": 5, "duration_seconds": 200})

    assert client.get(f"/api/v1/sessions/{session_id}").json()["feedback_events"] == []


# --- The vocabulary -------------------------------------------------------------------------------


def test_energy_the_library_cannot_use_is_understood_refused_and_says_why(client, library_tracks):
    """The words were understood: the library cannot act on them. That is INTENT_UNAVAILABLE, not MESSAGE_NOT_UNDERSTOOD."""
    session_id, _ = _playing(client)
    before = client.get(f"/api/v1/sessions/{session_id}").json()

    response = _turn(client, session_id, kind="message", text="a bit calmer")

    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "INTENT_UNAVAILABLE"
    assert error["message"] == "Your library doesn't describe energy yet, so that can't change what plays. Try a genre."
    assert error["details"] == {"unavailable": ["energy"], "dimensions": ["genre"]}
    assert client.get(f"/api/v1/sessions/{session_id}").json() == before


def test_typed_and_structured_intent_the_library_cannot_use_get_the_same_answer(client, library_tracks):
    session_id, _ = _playing(client)

    typed = _error(_turn(client, session_id, kind="message", text="something focused"))
    structured = _error(_turn(client, session_id, kind="refine", context={"temporary_genres": ["Ambient"], "temporary_moods": ["Focused"]}))
    started = _error(_start(client, message="something focused"))

    answers = [{key: error[key] for key in ("code", "message", "details")} for error in (typed, structured, started)]
    assert answers[0] == answers[1] == answers[2] == {
        "code": "INTENT_UNAVAILABLE",
        "message": "Your library doesn't describe that mood yet, so that can't change what plays. Try a genre.",
        "details": {"unavailable": ["mood"], "dimensions": ["genre"]},
    }


def test_the_vocabulary_offers_the_librarys_genres_the_curated_moods_and_the_energy_scale(client, library_tracks):
    body = client.get("/api/v1/listening/vocabulary").json()

    assert body["library"] == {"ready": True, "playable_tracks": 6}
    # Genre tags exist; nothing declares a mood, and nothing measures the five features yet.
    assert body["dimensions"] == {
        "mood": "no_data", "genre": "usable", "energy": "no_data",
        "danceability": "no_data", "tempo": "no_data", "valence": "no_data", "acousticness": "no_data",
    }
    assert body["usable_moods"] == []
    assert body["unmapped_fields"] == ["current_mood", "listening_goal", "activity"]

    assert body["genres"] == ["Ambient", "Jazz"]
    assert body["moods"] == ["Emotional", "Focused", "Calm", "Joyful", "Driven"]
    assert [(level["id"], level["target_energy"]) for level in body["energy"]] == [
        ("very-low", 0.1), ("low", 0.3), ("medium", 0.5), ("high", 0.7), ("very-high", 0.9)
    ]


@pytest.mark.parametrize("text", ["anything", "surprise me", "some jazz", "a bit calmer"])
def test_an_empty_library_is_not_ready_rather_than_unsupported(client, text):
    body = client.get("/api/v1/listening/vocabulary").json()

    assert body["library"] == {"ready": False, "playable_tracks": 0}
    assert set(body["dimensions"].values()) == {"library_not_ready"}  # no dimension is called unsupported
    assert (body["genres"], body["usable_moods"]) == ([], [])
    response = _start(client, message=text)
    assert (response.status_code, _error(response)["code"]) == (409, "LIBRARY_NOT_READY")
    assert client.get("/api/v1/sessions").json()["total"] == 0


def _store_track(api_settings, *labels):
    """A playable track stored directly, as a future source of labels would store it (the importer reads genre tags only)."""
    now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
    engine = create_database_engine(api_settings.database_url)
    try:
        unit_of_work = SqlAlchemyUnitOfWork(create_session_factory(engine))
        with unit_of_work:
            unit_of_work.tracks.add(Track(
                track_id=str(uuid.uuid4()), sha256=uuid.uuid4().hex * 2, size_bytes=1, audio_format=AudioFormat.FLAC,
                status=TrackStatus.READY, original_filename="still.flac", created_at=now, updated_at=now, title="Still",
                labels=tuple(TrackLabel(kind, value, "test", True) for kind, value in labels),
            ))
            unit_of_work.commit()
    finally:
        engine.dispose()


def test_a_track_whose_mood_is_one_of_tunes_makes_mood_supported(client, api_settings):
    _store_track(api_settings, (LabelKind.GENRE, "Ambient"), (LabelKind.MOOD, "Calm"))

    vocabulary = client.get("/api/v1/listening/vocabulary").json()
    assert {key: vocabulary["dimensions"][key] for key in ("mood", "genre", "energy")} == {"mood": "usable", "genre": "usable", "energy": "no_data"}
    assert vocabulary["usable_moods"] == ["Calm"]  # only the moods a track declares can change what plays
    assert _start(client, context={"temporary_moods": ["Calm"]}).status_code == 201
    assert _error(_start(client, context={"temporary_moods": ["Joyful"]}))["details"] == {"unavailable": ["mood"], "dimensions": ["mood", "genre"]}


def test_playable_music_without_genre_tags_is_ready_with_genre_unavailable(client, api_settings):
    """Tracks exist but none declares a genre: the library is ready, and only genre is unavailable for now."""
    _store_track(api_settings)

    vocabulary = client.get("/api/v1/listening/vocabulary").json()
    assert (vocabulary["library"], vocabulary["dimensions"]["genre"]) == ({"ready": True, "playable_tracks": 1}, "no_data")
    refused = _start(client, context={"temporary_genres": ["Jazz"]})
    assert (refused.status_code, _error(refused)["code"], _error(refused)["details"]) == (422, "INTENT_UNAVAILABLE", {"unavailable": ["genre"], "dimensions": []})
    assert _error(_start(client, message="the weather"))["message"] == 'Intentune can\'t act on that yet. Try "surprise me".'
    assert _start(client, message="surprise me").status_code == 201  # exploration needs no data


def test_a_library_mood_outside_tunes_five_makes_mood_usable_and_typed_words_can_use_it(client, api_settings):
    """B10 carry-forward: any real mood label makes the dimension usable; Tune still offers only its five, where present."""
    _store_track(api_settings, (LabelKind.GENRE, "Ambient"), (LabelKind.MOOD, "Dreamy"))
    _store_track(api_settings, (LabelKind.GENRE, "Jazz"), (LabelKind.MOOD, "Melancholic"))

    vocabulary = client.get("/api/v1/listening/vocabulary").json()
    assert (vocabulary["dimensions"]["mood"], vocabulary["usable_moods"]) == ("usable", [])
    started = _start(client, message="something dreamy")
    assert started.status_code == 201
    assert started.json()["session"]["context"]["temporary_moods"] == ["Dreamy"]
    refused = _start(client, context={"temporary_moods": ["Calm"]})  # a curated mood the library does not have
    assert (_error(refused)["code"], _error(refused)["details"]["unavailable"]) == ("INTENT_UNAVAILABLE", ["mood"])
