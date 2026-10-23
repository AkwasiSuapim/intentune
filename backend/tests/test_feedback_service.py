"""FeedbackService application tests against a migrated SQLite database (Prototype 1, phase B6).

Execution guide §9: each piece of feedback is persisted as a raw fact, then
interpreted, then the session's evidence changes and the queue is re-ranked at
once. These tests drive the whole path through the real repositories:
- what is stored (raw facts only);
- what playback does (a skip, completion, or Not for me about the playing
  track moves on; Replay plays a past track again);
- how the next tracks change.

The interpretation rules themselves, with their boundaries, are covered in
test_feedback_policy.py.
"""

import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.intentune.application.adaptation import LongTermAdaptationService
from src.intentune.application.feedback import FeedbackService
from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.policy import EvidenceBasis
from src.intentune.domain.session import (
    LISTENER_REPLAY_ALGORITHM,
    FeedbackEventType,
    InvalidSessionTransition,
    OccurrenceStatus,
    RecommendationOccurrenceNotFound,
    SessionNotFound,
    TurnKind,
)

_NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
_AMBIENT = ListeningContext(temporary_genres=("ambient",))


class SteppingClock:
    def __init__(self):
        self._now = _NOW

    def __call__(self):
        self._now += timedelta(seconds=1)
        return self._now


class _FixedRandom(random.Random):
    def __init__(self, value):
        super().__init__(0)
        self.value = value

    def random(self):
        return self.value


@pytest.fixture
def clock():
    return SteppingClock()


@pytest.fixture
def sessions(unit_of_work, clock):
    return SessionService(unit_of_work, clock=clock)


@pytest.fixture
def recommender(unit_of_work, clock):
    """Policy v1 that never explores automatically, so each queue below is fully determined."""
    return RecommendationService(unit_of_work, rng=_FixedRandom(0.999), clock=clock)


@pytest.fixture
def feedback(unit_of_work, recommender, clock):
    return FeedbackService(unit_of_work, recommender, LongTermAdaptationService(unit_of_work, clock=clock), clock=clock)


@pytest.fixture
def listener(unit_of_work):
    return ensure_default_listener(unit_of_work).listener_profile_id


@pytest.fixture
def ids(unit_of_work):
    """Ambient tracks by six artists: three dark ones (a*) that sort first, and three calm ones (b*)."""
    titles = {}
    with unit_of_work:
        for title, mood in (("a1", "dark"), ("a2", "dark"), ("a3", "dark"), ("b1", "calm"), ("b2", "calm"), ("b3", "calm")):
            track = Track(
                track_id=str(uuid.uuid4()), sha256=hashlib.sha256(title.encode()).hexdigest(), size_bytes=10,
                audio_format=AudioFormat.FLAC, status=TrackStatus.READY, original_filename=f"{title}.flac",
                created_at=_NOW, updated_at=_NOW, title=title, artist=f"Artist {title}", analysis_version="test@1",
                labels=(TrackLabel(LabelKind.GENRE, "ambient", "tag", True), TrackLabel(LabelKind.MOOD, mood, "tag", True)),
            )
            unit_of_work.tracks.add(track)
            titles[title] = track.track_id
        unit_of_work.commit()
    return titles


def _titles(occurrences, ids):
    title_of = {track_id: title for title, track_id in ids.items()}
    return [title_of[occurrence.track_id] for occurrence in occurrences]


@pytest.fixture
def playing_session(sessions, recommender, listener, ids):
    """An ambient session with a1 playing and a2, a3, b1 queued."""
    session_id = sessions.start_session(listener, _AMBIENT).session.session_id
    recommender.refresh_queue(session_id)
    sessions.advance(session_id)
    state = recommender.refresh_queue(session_id)
    assert (_titles([state.playing], ids), _titles(state.queue, ids)) == (["a1"], ["a2", "a3", "b1"])
    return session_id, state


# --- Reactions ------------------------------------------------------------------------------------


def test_a_like_is_stored_as_a_raw_fact_and_re_ranks_at_once(feedback, sessions, ids, playing_session):
    session_id, state = playing_session
    calm = state.queue[2]

    outcome = feedback.react(session_id, calm.occurrence_id, FeedbackEventType.LIKE)

    assert _titles(outcome.state.queue, ids) == ["b1", "b2", "b3"]  # tracks like the liked one, at once
    assert outcome.state.playing.occurrence_id == state.playing.occurrence_id  # a Like does not touch playback
    assert (outcome.event_weight, outcome.interpretation.basis, outcome.interpretation.weight) == (1.0, EvidenceBasis.EXPLICIT, 1.0)
    [stored] = sessions.history(session_id).feedback_events
    assert (stored.event_type, stored.occurrence_id, stored.played_seconds, stored.played_fraction) == (
        FeedbackEventType.LIKE, calm.occurrence_id, None, None
    )


def test_an_unlike_is_stored_after_the_like_and_takes_it_back(feedback, sessions, ids, playing_session):
    """B9: both raw facts stay stored; the queue goes back to what it was before the Like."""
    session_id, state = playing_session
    calm = state.queue[2]
    feedback.react(session_id, calm.occurrence_id, FeedbackEventType.LIKE)

    outcome = feedback.react(session_id, calm.occurrence_id, FeedbackEventType.UNLIKE)

    assert (outcome.event_weight, outcome.interpretation.weight, outcome.interpretation.basis) == (0.0, 0.0, EvidenceBasis.NONE)
    assert outcome.interpretation.excluded is False
    assert _titles(outcome.state.queue, ids) == ["a2", "a3", "b1"]  # as before the Like
    assert outcome.state.playing.occurrence_id == state.playing.occurrence_id  # an Unlike does not touch playback
    assert [event.event_type for event in sessions.history(session_id).feedback_events] == [
        FeedbackEventType.LIKE, FeedbackEventType.UNLIKE
    ]


def test_a_save_is_as_strong_as_a_like(feedback, ids, playing_session):
    session_id, state = playing_session

    outcome = feedback.react(session_id, state.queue[2].occurrence_id, FeedbackEventType.SAVE)

    assert (outcome.event_weight, outcome.interpretation.weight) == (1.0, 1.0)
    assert _titles(outcome.state.queue, ids) == ["b1", "b2", "b3"]


def test_not_for_me_about_the_playing_track_moves_on_and_keeps_it_out_for_the_session(feedback, sessions, recommender, listener, ids, playing_session):
    session_id, state = playing_session
    rejected = state.playing

    outcome = feedback.react(session_id, rejected.occurrence_id, FeedbackEventType.NOT_FOR_ME)

    assert _titles([outcome.state.playing], ids) == ["a2"]  # the next prepared track plays
    assert _titles(outcome.state.queue, ids) == ["b1", "b2", "b3"]  # tracks like the rejected one go down
    assert (outcome.interpretation.weight, outcome.interpretation.excluded) == (-1.0, True)
    for _ in range(4):
        state = recommender.refresh_queue(session_id)
        assert rejected.track_id not in {occurrence.track_id for occurrence in state.queue}
        sessions.advance(session_id)

    # Not for me changes nothing beyond the session: a new session may play the track again.
    fresh = sessions.start_session(listener, _AMBIENT).session.session_id
    assert rejected.track_id in {occurrence.track_id for occurrence in recommender.refresh_queue(fresh).queue}


def test_not_for_me_about_a_queued_track_leaves_playback_alone(feedback, ids, playing_session):
    session_id, state = playing_session

    outcome = feedback.react(session_id, state.queue[0].occurrence_id, FeedbackEventType.NOT_FOR_ME)

    assert outcome.state.playing.occurrence_id == state.playing.occurrence_id
    assert "a2" not in _titles(outcome.state.queue, ids)


# --- Playback endings ---------------------------------------------------------------------------------


def test_an_early_skip_moves_on_and_lowers_tracks_like_it(feedback, sessions, ids, playing_session):
    session_id, state = playing_session

    outcome = feedback.report_playback(session_id, state.playing.occurrence_id, FeedbackEventType.SKIP, 10.0, 100.0)

    assert _titles([outcome.state.playing], ids) == ["a2"]  # the prepared next track begins (spec §22)
    assert _titles(outcome.state.queue, ids) == ["b1", "b2", "b3"]  # the rest is re-ranked away from a1
    assert (outcome.event_weight, outcome.interpretation.basis) == (-0.50, EvidenceBasis.PASSIVE)
    [stored] = sessions.history(session_id).feedback_events
    assert (stored.event_type, stored.played_seconds, stored.duration_seconds, stored.played_fraction) == (FeedbackEventType.SKIP, 10.0, 100.0, 0.10)
    statuses = {occurrence.occurrence_id: occurrence.status for occurrence in sessions.history(session_id).occurrences}
    assert statuses[state.playing.occurrence_id] is OccurrenceStatus.PLAYED


def test_a_skip_within_the_grace_period_moves_on_without_evidence(feedback, ids, playing_session):
    session_id, state = playing_session

    outcome = feedback.report_playback(session_id, state.playing.occurrence_id, FeedbackEventType.SKIP, 8.0, 240.0)

    assert (outcome.event_weight, outcome.interpretation.basis) == (0.0, EvidenceBasis.GRACE)
    assert _titles([outcome.state.playing], ids) == ["a2"]
    # Ranked as if nothing had been said: every track keeps a neutral session fit.
    assert all(occurrence.score == pytest.approx((0.55 * 1.0 + 0.30 * 0.5) / 0.85) for occurrence in outcome.state.queue)


def test_a_completed_track_is_positive_evidence(feedback, ids, playing_session):
    session_id, state = playing_session

    outcome = feedback.report_playback(session_id, state.playing.occurrence_id, FeedbackEventType.COMPLETE, 240.0, 240.0)

    assert (outcome.event_weight, outcome.interpretation.weight) == (0.80, 0.80)
    assert _titles([outcome.state.playing], ids) == ["a2"]
    assert _titles(outcome.state.queue, ids)[0] == "a3"  # a track like the completed one comes next


def test_an_explicit_action_takes_precedence_over_the_skip_that_follows(feedback, ids, playing_session):
    session_id, state = playing_session
    feedback.react(session_id, state.playing.occurrence_id, FeedbackEventType.LIKE)

    outcome = feedback.report_playback(session_id, state.playing.occurrence_id, FeedbackEventType.SKIP, 10.0, 100.0)

    assert outcome.event_weight == -0.50  # the skip on its own
    assert (outcome.interpretation.weight, outcome.interpretation.basis) == (1.0, EvidenceBasis.EXPLICIT)  # the Like decides
    assert _titles(outcome.state.queue, ids)[0] == "a3"


def test_a_like_on_an_upcoming_card_decides_when_that_track_later_plays_and_is_skipped(feedback, sessions, ids, playing_session):
    """The Like re-ranked the queue, so b1 was surfaced again as a new occurrence before it played."""
    session_id, state = playing_session
    liked = feedback.react(session_id, state.queue[2].occurrence_id, FeedbackEventType.LIKE)
    assert liked.state.queue[0].occurrence_id != state.queue[2].occurrence_id  # a new occurrence of b1
    now_b1 = feedback.report_playback(session_id, state.playing.occurrence_id, FeedbackEventType.SKIP, 100.0, 100.0).state.playing
    assert _titles([now_b1], ids) == ["b1"]

    outcome = feedback.report_playback(session_id, now_b1.occurrence_id, FeedbackEventType.SKIP, 10.0, 100.0)

    assert (outcome.event_weight, outcome.interpretation.weight, outcome.interpretation.basis) == (-0.50, 1.0, EvidenceBasis.EXPLICIT)
    # Evidence is combined per track, but each raw event stays stored with the occurrence it was about (for B10, B11).
    stored = [(event.event_type, event.occurrence_id) for event in sessions.history(session_id).feedback_events]
    assert stored == [
        (FeedbackEventType.LIKE, state.queue[2].occurrence_id),
        (FeedbackEventType.SKIP, state.playing.occurrence_id),
        (FeedbackEventType.SKIP, now_b1.occurrence_id),
    ]


def test_a_late_report_about_a_finished_track_does_not_move_playback_again(feedback, sessions, ids, playing_session):
    """NEXT already moved on; the player then reports how far the skipped track got."""
    session_id, state = playing_session
    sessions.apply_turn(session_id, TurnKind.NEXT)
    now_playing = sessions.get_session(session_id).playing

    outcome = feedback.report_playback(session_id, state.playing.occurrence_id, FeedbackEventType.SKIP, 10.0, 100.0)

    assert outcome.state.playing.occurrence_id == now_playing.occurrence_id
    assert outcome.interpretation.weight == -0.50


# --- Replay ---------------------------------------------------------------------------------------


def test_replay_of_a_past_track_plays_it_again_now(feedback, sessions, ids, playing_session):
    """A fresh occurrence of the same track, chosen by the listener, ignoring the cooldown (spec §19)."""
    session_id, state = playing_session
    past = state.playing
    interrupted = sessions.advance(session_id).playing

    outcome = feedback.react(session_id, past.occurrence_id, FeedbackEventType.REPLAY)

    replaying = outcome.state.playing
    assert replaying.track_id == past.track_id and replaying.occurrence_id != past.occurrence_id
    assert (replaying.algorithm, replaying.score, replaying.rank, replaying.is_listener_replay) == (LISTENER_REPLAY_ALGORITHM, None, 1, True)
    statuses = {occurrence.occurrence_id: occurrence.status for occurrence in sessions.history(session_id).occurrences}
    assert (statuses[past.occurrence_id], statuses[interrupted.occurrence_id]) == (OccurrenceStatus.PLAYED, OccurrenceStatus.PLAYED)
    assert outcome.interpretation.weight == 1.0
    assert past.track_id not in {occurrence.track_id for occurrence in outcome.state.queue}  # it is playing


def test_a_replay_after_not_for_me_plays_the_track_manually_but_it_stays_out_of_automatic_recommendations(
    feedback, sessions, recommender, ids, playing_session
):
    """D18: the exact track stays excluded for the rest of the session. The Replay is the listener's own choice;
    it turns the evidence positive, but the policy still never queues the track itself."""
    session_id, state = playing_session
    rejected = state.playing
    feedback.react(session_id, rejected.occurrence_id, FeedbackEventType.NOT_FOR_ME)

    replayed = feedback.react(session_id, rejected.occurrence_id, FeedbackEventType.REPLAY)

    assert (replayed.state.playing.track_id, replayed.state.playing.is_listener_replay) == (rejected.track_id, True)
    assert (replayed.interpretation.weight, replayed.interpretation.excluded) == (1.0, True)
    # The positive evidence pulls a track like it to the front (a2, also similar, played after the Not for me and is cooling down).
    assert _titles(replayed.state.queue, ids)[0] == "a3"
    for _ in range(6):
        state = recommender.refresh_queue(session_id)
        assert rejected.track_id not in {occurrence.track_id for occurrence in state.queue}
        sessions.advance(session_id)
    automatic_plays = [occurrence for occurrence in sessions.history(session_id).occurrences if occurrence.track_id == rejected.track_id]
    assert [occurrence.algorithm for occurrence in automatic_plays] == ["policy-v1", LISTENER_REPLAY_ALGORITHM]


def test_replay_of_the_playing_track_changes_no_playback(feedback, ids, playing_session):
    session_id, state = playing_session

    outcome = feedback.react(session_id, state.playing.occurrence_id, FeedbackEventType.REPLAY)

    assert outcome.state.playing.occurrence_id == state.playing.occurrence_id


def test_a_replay_is_not_a_refresh_so_a_pending_control_still_applies(feedback, sessions, recommender, ids, playing_session):
    session_id, state = playing_session
    past = state.playing
    sessions.advance(session_id)
    sessions.apply_turn(session_id, TurnKind.MORE_FAMILIAR)

    feedback.react(session_id, past.occurrence_id, FeedbackEventType.REPLAY)

    assert recommender.last_decision.steering is TurnKind.MORE_FAMILIAR  # acted on by the refresh after the replay
    assert recommender.decide(session_id).steering is None


# --- What is refused, and leaves nothing behind ----------------------------------------------------


def test_feedback_that_needs_a_played_track_is_refused_for_one_that_never_played(feedback, sessions, playing_session):
    session_id, state = playing_session
    queued = state.queue[0]

    with pytest.raises(InvalidSessionTransition):
        feedback.report_playback(session_id, queued.occurrence_id, FeedbackEventType.SKIP, 10.0, 100.0)
    with pytest.raises(InvalidSessionTransition):
        feedback.react(session_id, queued.occurrence_id, FeedbackEventType.REPLAY)

    assert sessions.history(session_id).feedback_events == ()


@pytest.mark.parametrize(
    "call",
    [
        lambda feedback, session_id, occurrence_id: feedback.react(session_id, occurrence_id, FeedbackEventType.SKIP),
        lambda feedback, session_id, occurrence_id: feedback.report_playback(session_id, occurrence_id, FeedbackEventType.LIKE, 10.0, 100.0),
        lambda feedback, session_id, occurrence_id: feedback.report_playback(session_id, occurrence_id, FeedbackEventType.SKIP, -1.0, 100.0),
        lambda feedback, session_id, occurrence_id: feedback.report_playback(session_id, occurrence_id, FeedbackEventType.SKIP, 10.0, 0.0),
        lambda feedback, session_id, occurrence_id: feedback.report_playback(session_id, occurrence_id, FeedbackEventType.COMPLETE, None, None),
        lambda feedback, session_id, occurrence_id: feedback.react(session_id, occurrence_id, "PROGRESS"),
    ],
)
def test_malformed_feedback_is_refused(feedback, sessions, playing_session, call):
    session_id, state = playing_session

    with pytest.raises(ValueError):
        call(feedback, session_id, state.playing.occurrence_id)

    assert sessions.history(session_id).feedback_events == ()
    assert sessions.get_session(session_id).playing.occurrence_id == state.playing.occurrence_id


def test_feedback_needs_an_active_session_and_one_of_its_occurrences(feedback, sessions, listener, playing_session):
    session_id, state = playing_session
    other = sessions.start_session(listener, _AMBIENT).session.session_id  # ends the first session

    with pytest.raises(InvalidSessionTransition):
        feedback.react(session_id, state.playing.occurrence_id, FeedbackEventType.LIKE)
    with pytest.raises(RecommendationOccurrenceNotFound):
        feedback.react(other, state.playing.occurrence_id, FeedbackEventType.LIKE)
    with pytest.raises(SessionNotFound):
        feedback.react(str(uuid.uuid4()), state.playing.occurrence_id, FeedbackEventType.LIKE)


# --- Exploration, and the raw record ------------------------------------------------------------------


def test_an_early_skip_of_an_exploration_pick_lowers_the_automatic_rate(unit_of_work, sessions, listener, clock):
    """One skip halves the rate; it never stops exploration (spec §18)."""
    explorer = RecommendationService(unit_of_work, rng=_FixedRandom(0.0), clock=clock)
    feedback = FeedbackService(unit_of_work, explorer, LongTermAdaptationService(unit_of_work, clock=clock), clock=clock)
    with unit_of_work:
        for title, mood in (("c1", "calm"), ("c2", "calm"), ("c3", "calm"), ("d1", "dark")):
            unit_of_work.tracks.add(Track(
                track_id=str(uuid.uuid4()), sha256=hashlib.sha256(title.encode()).hexdigest(), size_bytes=10,
                audio_format=AudioFormat.FLAC, status=TrackStatus.READY, original_filename=f"{title}.flac", created_at=_NOW,
                updated_at=_NOW, title=title, artist=f"Artist {title}", analysis_version="test@1",
                labels=(TrackLabel(LabelKind.GENRE, "ambient", "tag", True), TrackLabel(LabelKind.MOOD, mood, "tag", True)),
            ))
        unit_of_work.commit()
    session_id = sessions.start_session(listener, _AMBIENT).session.session_id
    exploration = explorer.refresh_queue(session_id).queue[-1]
    assert exploration.is_exploration
    sessions.play(session_id, exploration.occurrence_id)

    feedback.report_playback(session_id, exploration.occurrence_id, FeedbackEventType.SKIP, 12.0, 200.0)

    assert explorer.decide(session_id).exploration_rate == pytest.approx(0.05)


def test_feedback_events_are_kept_as_raw_history_in_order(feedback, sessions, engine, playing_session):
    session_id, state = playing_session
    feedback.react(session_id, state.queue[1].occurrence_id, FeedbackEventType.SAVE)
    feedback.report_playback(session_id, state.playing.occurrence_id, FeedbackEventType.COMPLETE, 251.0, 250.0)

    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT event_type, played_seconds, duration_seconds, played_fraction FROM feedback_events ORDER BY occurred_at"
        ).all()

    assert rows == [("SAVE", None, None, None), ("COMPLETE", 251.0, 250.0, 1.0)]  # the fraction is capped, the seconds kept
    events = sessions.history(session_id).feedback_events
    assert events[0].occurred_at < events[1].occurred_at
