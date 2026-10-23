"""Long-term adaptation (Prototype 1, phase B10) through the real use cases, against a migrated SQLite database.

Feedback reaches the long-term profile only through the existing backend use
cases (FeedbackService, ListeningService), which adapt between persisting the
raw fact and their single queue refresh. These tests drive that whole path:
- the gate, with Feedback Policy v1's per-track, per-session reading;
- the audit trail: policy version, before and after, reason, exact evidence;
- persistence across a restart, and the database's own guarantees;
- recomputation, reversal, and no drift;
- what Policy v1 ranks with the profile, and what still outranks it.

The library's tracks carry genres only (as the importer gives them), so these
exercise genre preference; numeric preferences are covered on synthetic
candidates in test_adaptation_policy.py.
"""

import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.intentune.application.adaptation import LongTermAdaptationService
from src.intentune.application.capability import IntentCapability
from src.intentune.application.feedback import FeedbackService
from src.intentune.application.listening import ListeningService
from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.adaptation import AdjustmentCause, AdjustmentChange, EvidenceReference, ProfileDimension
from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.domain.models import ListeningContext, MusicCandidate, Recommendation, ScoreBreakdown, ScoreComponent, UserProfile
from src.intentune.domain.policy import EvidenceBasis, interpretations_by_track
from src.intentune.domain.session import FeedbackEventType, TurnKind
from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork

_NOW = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)


class SteppingClock:
    def __init__(self):
        self._now = _NOW

    def __call__(self):
        self._now += timedelta(seconds=1)
        return self._now


class _NeverExplore(random.Random):
    def random(self):
        return 0.999


@pytest.fixture
def clock():
    return SteppingClock()


@pytest.fixture
def sessions(unit_of_work, clock):
    return SessionService(unit_of_work, clock=clock)


@pytest.fixture
def recommender(unit_of_work, clock):
    return RecommendationService(unit_of_work, rng=_NeverExplore(0), clock=clock)


@pytest.fixture
def adaptation(unit_of_work, clock):
    return LongTermAdaptationService(unit_of_work, clock=clock)


@pytest.fixture
def feedback(unit_of_work, recommender, adaptation, clock):
    return FeedbackService(unit_of_work, recommender, adaptation, clock=clock)


@pytest.fixture
def listening(sessions, recommender, unit_of_work, adaptation):
    return ListeningService(sessions, recommender, IntentCapability(unit_of_work), adaptation)


@pytest.fixture
def listener(unit_of_work):
    return ensure_default_listener(unit_of_work).listener_profile_id


@pytest.fixture
def ids(unit_of_work):
    """Six Afrobeats tracks (af*) and six Jazz tracks (jz*), each by its own artist, with no features beyond genre."""
    titles = {}
    with unit_of_work:
        for title, genre in [(f"af{n}", "Afrobeats") for n in range(1, 7)] + [(f"jz{n}", "Jazz") for n in range(1, 7)]:
            track = Track(
                track_id=str(uuid.uuid4()), sha256=hashlib.sha256(title.encode()).hexdigest(), size_bytes=10,
                audio_format=AudioFormat.FLAC, status=TrackStatus.READY, original_filename=f"{title}.flac",
                created_at=_NOW, updated_at=_NOW, title=title, artist=f"Artist {title}", analysis_version="test@1",
                labels=(TrackLabel(LabelKind.GENRE, genre, "tag", True),),
            )
            unit_of_work.tracks.add(track)
            titles[title] = track.track_id
        unit_of_work.commit()
    return titles


def _recommendation(track_id, rank):
    return Recommendation(
        candidate=MusicCandidate(candidate_id=track_id, title="t", creator="c", source="local"),
        score_breakdown=ScoreBreakdown(total_score=0.5, maximum_score=1.0, components=(ScoreComponent("intent", 0.5, 1.0, "intent fit 0.50"),)),
        rank=rank,
    )


def _session(sessions, listener, ids, *titles, context=ListeningContext()):
    """A new session with these tracks surfaced: (session_id, {title: occurrence_id})."""
    session_id = sessions.start_session(listener, context).session.session_id
    return session_id, _surface(sessions, ids, session_id, *titles)


def _surface(sessions, ids, session_id, *titles):
    title_of = {track_id: title for title, track_id in ids.items()}
    queue = sessions.queue_recommendations(session_id, [_recommendation(ids[title], rank) for rank, title in enumerate(titles, 1)], "policy-v1").queue
    return {title_of[occurrence.track_id]: occurrence.occurrence_id for occurrence in queue}


def _like(feedback, session_id, occurrences, *titles):
    for title in titles:
        feedback.react(session_id, occurrences[title], FeedbackEventType.LIKE)


def _afrobeats_established(sessions, feedback, listener, ids):
    """Two Likes in each of two sessions: the gate is met. Returns the second session and its occurrences."""
    first, surfaced = _session(sessions, listener, ids, "af1", "af2")
    _like(feedback, first, surfaced, "af1", "af2")
    second, surfaced = _session(sessions, listener, ids, "af3", "af4", "af5")
    _like(feedback, second, surfaced, "af3", "af4")
    return second, surfaced


def _play_to(sessions, feedback, ids, session_id, title, fraction, ending=FeedbackEventType.COMPLETE):
    """Surface one track, play it, and report how far it played (of 200 seconds)."""
    [occurrence] = _surface(sessions, ids, session_id, title).values()
    sessions.play(session_id, occurrence)
    feedback.report_playback(session_id, occurrence, ending, 200.0 * fraction, 200.0)
    return occurrence


# --- The gate ----------------------------------------------------------------------------------------------


def test_the_profile_waits_for_four_strong_signals_across_two_sessions_then_changes_once(sessions, feedback, adaptation, listener, ids):
    first, surfaced = _session(sessions, listener, ids, "af1", "af2", "af3", "af4")
    _like(feedback, first, surfaced, "af1", "af2", "af3", "af4")
    assert (adaptation.profile(listener), adaptation.adjustments(listener)) == (None, [])  # four, but one session

    second, surfaced = _session(sessions, listener, ids, "af5", "af6")
    feedback.react(second, surfaced["af5"], FeedbackEventType.LIKE)

    [adjustment] = adaptation.adjustments(listener)
    assert adaptation.profile(listener) == UserProfile(preferred_genres=("Afrobeats",))
    assert (adjustment.dimension, adjustment.change, adjustment.subject) == (ProfileDimension.GENRE, AdjustmentChange.ADDED, "Afrobeats")
    feedback.react(second, surfaced["af6"], FeedbackEventType.LIKE)
    assert len(adaptation.adjustments(listener)) == 1  # more of the same evidence changes nothing further


@pytest.mark.parametrize("likes", [1, 2, 3])
def test_fewer_than_four_strong_signals_change_nothing(sessions, feedback, adaptation, listener, ids, likes):
    first, surfaced = _session(sessions, listener, ids, "af1", "af2")
    _like(feedback, first, surfaced, *["af1", "af2"][: min(likes, 2)])
    if likes == 3:
        second, surfaced = _session(sessions, listener, ids, "af3")
        _like(feedback, second, surfaced, "af3")

    assert adaptation.adjustments(listener) == []


def test_two_genres_with_two_signals_each_are_not_four_of_anything(sessions, feedback, adaptation, listener, ids):
    first, surfaced = _session(sessions, listener, ids, "af1", "jz1")
    _like(feedback, first, surfaced, "af1", "jz1")
    second, surfaced = _session(sessions, listener, ids, "af2", "jz2")
    _like(feedback, second, surfaced, "af2", "jz2")

    assert adaptation.adjustments(listener) == []


def test_many_actions_about_one_track_in_one_session_count_once(sessions, feedback, adaptation, listener, ids):
    """A Like, a Save, three playlist adds, and a run of Replays about one track: one effective item, not six."""
    first, surfaced = _session(sessions, listener, ids, "af1")
    feedback.react(first, surfaced["af1"], FeedbackEventType.LIKE)
    feedback.react(first, surfaced["af1"], FeedbackEventType.SAVE)
    for _ in range(3):
        feedback.record_playlist_add(first, surfaced["af1"])
    second, surfaced = _session(sessions, listener, ids, "af2")
    sessions.play(second, surfaced["af2"])
    for _ in range(5):
        feedback.react(second, surfaced["af2"], FeedbackEventType.REPLAY)
    assert adaptation.adjustments(listener) == []
    assert len(adaptation.derive(listener).evidence) == 2

    third, surfaced = _session(sessions, listener, ids, "af3", "af4")
    _like(feedback, third, surfaced, "af3", "af4")
    [adjustment] = adaptation.adjustments(listener)
    assert len(adjustment.evidence) == 4


# --- Feedback semantics -------------------------------------------------------------------------------------


def test_an_unlike_cancels_its_like_and_is_never_negative_evidence(sessions, feedback, adaptation, listener, ids):
    second, surfaced = _afrobeats_established(sessions, feedback, listener, ids)

    feedback.react(second, surfaced["af4"], FeedbackEventType.UNLIKE)

    added, removed = adaptation.adjustments(listener)
    assert (removed.change, removed.cause, removed.previous, removed.resulting) == (AdjustmentChange.REMOVED, AdjustmentCause.GATE_LOST, ("Afrobeats",), ())
    assert len(removed.evidence) == 3  # three Likes remain; the Unlike did not count against them
    assert adaptation.profile(listener) == UserProfile()
    assert [event.event_type for event in sessions.history(second).feedback_events].count(FeedbackEventType.LIKE) == 2  # raw history intact
    feedback.react(second, surfaced["af5"], FeedbackEventType.LIKE)  # one more Like is enough again: net 4, not 3
    assert [item.change for item in adaptation.adjustments(listener)] == [AdjustmentChange.ADDED, AdjustmentChange.REMOVED, AdjustmentChange.ADDED]


def test_not_for_me_is_strong_negative_evidence_as_an_event_or_a_turn(sessions, feedback, listening, adaptation, listener, ids):
    second, surfaced = _afrobeats_established(sessions, feedback, listener, ids)

    listening.steer(second, TurnKind.NOT_FOR_ME, occurrence_id=surfaced["af5"])  # the turn path

    removed = adaptation.adjustments(listener)[-1]
    assert (removed.change, removed.cause) == (AdjustmentChange.REMOVED, AdjustmentCause.GATE_LOST)
    [refusal] = [reference for reference in removed.evidence if reference.weight < 0]
    assert refusal.session_turn_id == sessions.history(second).turns[-1].turn_id and refusal.feedback_event_id is None
    third, surfaced = _session(sessions, listener, ids, "af6", "jz1")
    _like(feedback, third, surfaced, "af6")  # net back to 4
    feedback.react(third, surfaced["af6"], FeedbackEventType.NOT_FOR_ME)  # the event path takes the same track's Like over
    assert adaptation.profile(listener) == UserProfile()


def test_skips_and_partial_plays_never_count_while_full_plays_do(sessions, feedback, adaptation, listener, ids):
    first = sessions.start_session(listener, ListeningContext()).session.session_id
    _play_to(sessions, feedback, ids, first, "af1", 0.05, FeedbackEventType.SKIP)  # early skip: medium negative
    _play_to(sessions, feedback, ids, first, "af2", 0.80)  # 75-89%: medium positive
    _play_to(sessions, feedback, ids, first, "af3", 0.95)
    second = sessions.start_session(listener, ListeningContext()).session.session_id
    _play_to(sessions, feedback, ids, second, "af4", 0.50)  # weak
    _play_to(sessions, feedback, ids, second, "af5", 0.92)
    assert adaptation.adjustments(listener) == []  # two full plays; the partial ones are not strong

    _play_to(sessions, feedback, ids, second, "af6", 1.0)
    _play_to(sessions, feedback, ids, second, "jz1", 0.99)
    assert adaptation.adjustments(listener) == []  # three full Afrobeats plays and one Jazz: not four of one
    third, surfaced = _session(sessions, listener, ids, "af2")
    _like(feedback, third, surfaced, "af2")  # af2 was only a medium play in the first session; this Like is strong

    [adjustment] = adaptation.adjustments(listener)
    assert adjustment.subject == "Afrobeats" and len(adjustment.evidence) == 4


def test_more_like_this_steers_the_session_but_never_reaches_the_long_term_gate(sessions, listening, adaptation, listener, ids):
    """Four More like this turns about four tracks across two sessions: strong session evidence, no long-term evidence."""
    for titles in (("af1", "af2"), ("af3", "af4")):
        session_id, surfaced = _session(sessions, listener, ids, *titles)
        for title in titles:
            listening.steer(session_id, TurnKind.MORE_LIKE_THIS, occurrence_id=surfaced[title])

    history = sessions.history(session_id)
    reading = interpretations_by_track(history.turns, history.occurrences, history.feedback_events)
    assert {(item.basis, item.weight) for item in reading.values()} == {(EvidenceBasis.EXPLICIT, 1.0)}  # still session evidence
    assert adaptation.derive(listener).evidence == ()
    assert adaptation.adjustments(listener) == []


def test_a_like_followed_by_more_like_this_is_one_long_term_item_from_the_like(sessions, feedback, listening, adaptation, listener, ids):
    session_id, surfaced = _session(sessions, listener, ids, "af1")
    feedback.react(session_id, surfaced["af1"], FeedbackEventType.LIKE)
    listening.steer(session_id, TurnKind.MORE_LIKE_THIS, occurrence_id=surfaced["af1"])

    [item] = adaptation.derive(listener).evidence

    [like] = sessions.history(session_id).feedback_events
    assert (item.feedback_event_id, item.session_turn_id, item.weight) == (like.event_id, None, 1.0)


def test_one_favourite_track_across_sessions_never_sets_a_genre_preference_until_another_joins(sessions, feedback, adaptation, listener, ids):
    for _ in range(4):
        session_id, surfaced = _session(sessions, listener, ids, "af1")
        _like(feedback, session_id, surfaced, "af1")
    assert adaptation.adjustments(listener) == []  # four sessions, one song

    session_id, surfaced = _session(sessions, listener, ids, "af2")
    _like(feedback, session_id, surfaced, "af2")

    [adjustment] = adaptation.adjustments(listener)
    assert adjustment.subject == "Afrobeats"
    assert {reference.track_id for reference in adjustment.evidence} == {ids["af1"], ids["af2"]} and len(adjustment.evidence) == 5


def test_genre_only_tracks_change_the_genre_preference_and_no_numeric_one(sessions, feedback, adaptation, listener, ids):
    _afrobeats_established(sessions, feedback, listener, ids)

    profile = adaptation.profile(listener)

    assert profile.preferred_genres == ("Afrobeats",)
    assert (profile.preferred_moods, profile.preferred_energy, profile.preferred_danceability, profile.preferred_tempo_bpm,
            profile.preferred_valence, profile.preferred_acousticness) == ((), None, None, None, None, None)
    assert {item.dimension for item in adaptation.adjustments(listener)} == {ProfileDimension.GENRE}


# --- The audit trail ------------------------------------------------------------------------------------------


def test_an_adjustment_records_its_version_before_and_after_reason_and_exact_evidence(sessions, feedback, adaptation, listener, ids):
    first, surfaced = _session(sessions, listener, ids, "af1", "af2")
    _like(feedback, first, surfaced, "af1", "af2")
    second, surfaced = _session(sessions, listener, ids, "af3", "af4")
    _like(feedback, second, surfaced, "af3", "af4")

    [adjustment] = adaptation.adjustments(listener)

    likes = sessions.history(first).feedback_events + sessions.history(second).feedback_events
    assert adjustment.evidence == tuple(
        EvidenceReference(event.session_id, ids[title], 1.0, feedback_event_id=event.event_id)
        for event, title in zip(likes, ("af1", "af2", "af3", "af4"))
    )
    assert (adjustment.listener_profile_id, adjustment.sequence, adjustment.policy_version) == (listener, 1, "adaptation-v1")
    assert (adjustment.previous, adjustment.resulting, adjustment.cause) == ((), ("Afrobeats",), AdjustmentCause.GATE_MET)
    assert adjustment.reason == (
        "meets the gate: 4 strong positive and 0 strong negative signals for genre 'Afrobeats': net 4 (needs 4), "
        "positive evidence from 2 session(s) (needs 2) about 4 track(s) (needs 2)"
    )
    assert adjustment.created_at > likes[-1].occurred_at
    stored = adaptation.stored(listener)
    assert (stored.policy_version, stored.updated_at) == ("adaptation-v1", adjustment.created_at)


def test_the_profile_and_its_audit_trail_survive_a_restart(sessions, feedback, adaptation, listener, ids, migrated_database_url, engine):
    _afrobeats_established(sessions, feedback, listener, ids)
    before = (adaptation.profile(listener), adaptation.adjustments(listener))
    engine.dispose()

    restarted = create_database_engine(migrated_database_url)
    try:
        after = LongTermAdaptationService(SqlAlchemyUnitOfWork(create_session_factory(restarted)))
        assert (after.profile(listener), after.adjustments(listener)) == before
        assert after.adapt(listener) == ()  # nothing new to learn after a restart
    finally:
        restarted.dispose()


def test_the_database_refuses_an_inconsistent_audit_trail(sessions, feedback, adaptation, listener, ids, engine):
    _afrobeats_established(sessions, feedback, listener, ids)
    [adjustment] = adaptation.adjustments(listener)
    reference = adjustment.evidence[0]
    insert_evidence = (
        "INSERT INTO long_term_adjustment_evidence (adjustment_id, position, session_id, track_id, feedback_event_id, session_turn_id, weight) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    unknown = str(uuid.uuid4())
    refused = [
        (insert_evidence, (adjustment.adjustment_id, 9, reference.session_id, reference.track_id, unknown, None, 1.0)),  # no such event
        (insert_evidence, (unknown, 0, reference.session_id, reference.track_id, reference.feedback_event_id, None, 1.0)),  # no such adjustment
        (insert_evidence, (adjustment.adjustment_id, 9, reference.session_id, reference.track_id, None, None, 1.0)),  # no raw fact
        (insert_evidence, (adjustment.adjustment_id, 9, reference.session_id, ids["jz1"], reference.feedback_event_id, None, 0.0)),  # zero weight
        (insert_evidence, (adjustment.adjustment_id, 9, reference.session_id, reference.track_id, reference.feedback_event_id, None, 1.0)),  # same item twice
        (
            "INSERT INTO long_term_adjustments (id, listener_profile_id, sequence, dimension, change, cause, subject, previous_json, "
            "resulting_json, reason, policy_version, created_at) VALUES (?, ?, 1, 'ENERGY', 'SET', 'GATE_MET', NULL, 'null', '0.5', 'r', 'v', '2026-10-22 10:00:00')",
            (str(uuid.uuid4()), listener),
        ),  # the sequence is taken
        (
            "INSERT INTO long_term_adjustments (id, listener_profile_id, sequence, dimension, change, cause, subject, previous_json, "
            "resulting_json, reason, policy_version, created_at) VALUES (?, ?, 2, 'GENRE', 'ADDED', 'GATE_MET', NULL, '[]', '[]', 'r', 'v', '2026-10-22 10:00:00')",
            (str(uuid.uuid4()), listener),
        ),  # a genre change names its value
    ]
    for statement, values in refused:
        with engine.connect() as connection:
            with pytest.raises(IntegrityError):
                connection.exec_driver_sql(statement, values)


# --- Recomputation ------------------------------------------------------------------------------------------------


def test_adapting_again_without_new_evidence_records_nothing(sessions, feedback, adaptation, listener, ids):
    _afrobeats_established(sessions, feedback, listener, ids)
    count = len(adaptation.adjustments(listener))

    for _ in range(3):
        assert adaptation.adapt(listener) == ()

    assert len(adaptation.adjustments(listener)) == count
    assert adaptation.derive(listener).profile == adaptation.profile(listener)


def test_a_rebuild_from_the_same_history_gives_the_same_profile(sessions, feedback, adaptation, listener, ids, engine):
    _afrobeats_established(sessions, feedback, listener, ids)
    stored = adaptation.profile(listener)
    with engine.begin() as connection:  # lose the materialized state and its history, keeping the raw history
        for table in ("long_term_adjustment_evidence", "long_term_adjustments", "long_term_profiles"):
            connection.exec_driver_sql(f"DELETE FROM {table}")

    rebuilt = adaptation.adapt(listener)

    assert adaptation.profile(listener) == stored
    assert [(item.change, item.subject, len(item.evidence)) for item in rebuilt] == [(AdjustmentChange.ADDED, "Afrobeats", 4)]


# --- What Policy v1 ranks with -------------------------------------------------------------------------------------


def _top(recommender, session_id, ids):
    title_of = {track_id: title for title, track_id in ids.items()}
    return [title_of[pick.candidate.music.candidate_id] for pick in recommender.decide(session_id).picks]


def test_without_long_term_history_policy_v1_ranks_exactly_as_before(sessions, recommender, listener, ids):
    session_id = sessions.start_session(listener, ListeningContext()).session.session_id

    decision = recommender.decide(session_id)

    assert all(pick.score.long_term is None for pick in decision.picks)
    assert all("long_term" not in [name for name, _, _ in pick.score.stage_weights] for pick in decision.picks)


def test_a_new_session_ranks_with_the_stored_profile_as_the_separate_long_term_stage(sessions, feedback, recommender, listener, ids):
    _afrobeats_established(sessions, feedback, listener, ids)
    session_id = sessions.start_session(listener, ListeningContext()).session.session_id  # nothing asked for

    decision = recommender.decide(session_id)

    assert _top(recommender, session_id, ids)[:3] == ["af1", "af2", "af3"]
    first = decision.picks[0].score
    assert first.intent is None and first.long_term.value == 1.0
    assert [(name, round(weight, 4)) for name, weight, _ in first.stage_weights] == [("session", 0.6667), ("long_term", 0.3333)]


def test_current_explicit_intent_outweighs_a_conflicting_long_term_preference(sessions, feedback, recommender, listener, ids):
    _afrobeats_established(sessions, feedback, listener, ids)
    session_id = sessions.start_session(listener, ListeningContext(temporary_genres=("Jazz",))).session.session_id

    assert all(title.startswith("jz") for title in _top(recommender, session_id, ids))


def test_a_not_for_me_in_a_later_session_also_counts_against_the_long_term_preference(sessions, feedback, recommender, adaptation, listener, ids):
    """The refusal is session evidence and, being strong, long-term evidence too: the preference falls below the gate."""
    _afrobeats_established(sessions, feedback, listener, ids)
    session_id, surfaced = _session(sessions, listener, ids, "jz1", "af6")

    feedback.react(session_id, surfaced["jz1"], FeedbackEventType.LIKE)
    feedback.react(session_id, surfaced["af6"], FeedbackEventType.NOT_FOR_ME)

    assert adaptation.profile(listener) == UserProfile()
    assert all(title.startswith("jz") for title in _top(recommender, session_id, ids))


def test_with_no_intent_a_liked_genre_this_session_outranks_a_long_term_preference(sessions, feedback, recommender, adaptation, listener, ids):
    """History is positive affinity (TD-021): one Jazz Like this session beats the stored Afrobeats preference."""
    _afrobeats_established(sessions, feedback, listener, ids)
    session_id, surfaced = _session(sessions, listener, ids, "jz1")  # nothing asked for

    feedback.react(session_id, surfaced["jz1"], FeedbackEventType.LIKE)

    assert adaptation.profile(listener).preferred_genres == ("Afrobeats",)  # one Jazz Like changes no long-term preference
    decision = recommender.decide(session_id)
    assert all(title.startswith("jz") for title in _top(recommender, session_id, ids))
    assert decision.picks[0].score.combined == pytest.approx((0.30 * 1.0 + 0.15 * 0.5) / 0.45)
