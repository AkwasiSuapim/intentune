"""RecommendationService (Policy v1 queue refresh) application tests against a migrated SQLite database (phase B5).

refresh_queue() is the use case that turns a session's history into its next
three tracks: these tests drive it through SessionService turns and playback
and check what is surfaced and persisted (queue order, ranks, scores, the
policy version, exploration marks). The policy's own rules are covered in
test_policy.py; here the point is that the session's real history reaches
them, and that their result is stored correctly.
"""

import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.policy import POLICY_V1, signals_from_session
from src.intentune.domain.session import InvalidSessionTransition, OccurrenceStatus, SessionNotFound, TurnKind

_NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
_AMBIENT = ListeningContext(temporary_genres=("ambient",))
_INTENT_SHARE = 0.55 / 0.85
_SESSION_SHARE = 0.30 / 0.85


class SteppingClock:
    """A clock that advances one second per reading, so every change gets a distinct time."""

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
    """Policy v1 with exploration switched off, so each test's queue is fully determined."""
    return RecommendationService(unit_of_work, rng=_FixedRandom(0.999), clock=clock)


@pytest.fixture
def explorer(unit_of_work, clock):
    """Policy v1 that explores whenever its rate is above zero."""
    return RecommendationService(unit_of_work, rng=_FixedRandom(0.0), clock=clock)


@pytest.fixture
def listener(unit_of_work):
    return ensure_default_listener(unit_of_work).listener_profile_id


def _add_tracks(unit_of_work, *specs):
    """Add library tracks from (title, genre, mood, artist[, status]) and return {title: track_id}."""
    ids = {}
    with unit_of_work:
        for spec in specs:
            title, genre, mood, artist = spec[:4]
            status = spec[4] if len(spec) > 4 else TrackStatus.READY
            labels = []
            if genre is not None:
                labels.append(TrackLabel(LabelKind.GENRE, genre, "tag", True))
            if mood is not None:
                labels.append(TrackLabel(LabelKind.MOOD, mood, "tag", True))
            track = Track(
                track_id=str(uuid.uuid4()),
                sha256=hashlib.sha256(title.encode()).hexdigest(),
                size_bytes=10,
                audio_format=AudioFormat.FLAC,
                status=status,
                original_filename=f"{title}.flac",
                created_at=_NOW,
                updated_at=_NOW,
                title=title,
                artist=artist,
                analysis_version="test@1" if status is TrackStatus.READY else None,
                labels=tuple(labels),
            )
            unit_of_work.tracks.add(track)
            ids[title] = track.track_id
        unit_of_work.commit()
    return ids


def _titles(occurrences, ids):
    by_id = {track_id: title for title, track_id in ids.items()}
    return [by_id[occurrence.track_id] for occurrence in occurrences]


def _start(sessions, listener, context=_AMBIENT):
    return sessions.start_session(listener, context).session.session_id


# --- Refreshing the queue -------------------------------------------------------------------


def test_refresh_queues_the_policy_top_three_for_the_session_intent(unit_of_work, sessions, recommender, listener):
    ids = _add_tracks(unit_of_work, ("r1", "rock", None, "R"), ("a1", "ambient", None, "A"), ("a2", "ambient", None, "B"), ("a3", "ambient", None, "C"))
    session_id = _start(sessions, listener)

    state = recommender.refresh_queue(session_id)

    assert _titles(state.queue, ids) == ["a1", "a2", "a3"]
    assert [(occurrence.rank, occurrence.queue_position, occurrence.algorithm) for occurrence in state.queue] == [
        (1, 0, "policy-v1"), (2, 1, "policy-v1"), (3, 2, "policy-v1")
    ]
    assert all(occurrence.score == pytest.approx(_INTENT_SHARE + _SESSION_SHARE * 0.5) for occurrence in state.queue)
    assert not any(occurrence.is_exploration for occurrence in state.queue)
    assert state.playing is None


def test_deciding_alone_changes_nothing(unit_of_work, sessions, recommender, listener):
    _add_tracks(unit_of_work, ("a1", "ambient", None, "A"))
    session_id = _start(sessions, listener)

    decision = recommender.decide(session_id)

    assert len(decision.picks) == 1
    assert sessions.history(session_id).occurrences == ()


def test_a_refinement_re_ranks_and_replaces_the_queue(unit_of_work, sessions, recommender, listener):
    ids = _add_tracks(unit_of_work, ("a1", "ambient", None, "A"), ("a2", "ambient", None, "B"), ("r1", "rock", None, "C"), ("r2", "rock", None, "D"))
    session_id = _start(sessions, listener)
    before = recommender.refresh_queue(session_id).queue

    sessions.apply_turn(session_id, TurnKind.REFINE, ListeningContext(temporary_genres=("rock",)))
    after = recommender.refresh_queue(session_id).queue

    assert _titles(before, ids)[:2] == ["a1", "a2"]
    assert _titles(after, ids)[:2] == ["r1", "r2"]
    statuses = {occurrence.occurrence_id: occurrence.status for occurrence in sessions.history(session_id).occurrences}
    assert all(statuses[occurrence.occurrence_id] is OccurrenceStatus.REPLACED for occurrence in before)


def test_unavailable_tracks_are_not_queued(unit_of_work, sessions, recommender, listener):
    ids = _add_tracks(unit_of_work, ("gone", "ambient", None, "A", TrackStatus.MISSING_MANAGED_FILE), ("new", "ambient", None, "B", TrackStatus.IMPORTED))
    session_id = _start(sessions, listener)

    assert _titles(recommender.refresh_queue(session_id).queue, ids) == ["new"]


def test_refresh_needs_an_existing_active_session(unit_of_work, sessions, recommender, listener):
    _add_tracks(unit_of_work, ("a1", "ambient", None, "A"))
    session_id = _start(sessions, listener)
    sessions.end_session(session_id)

    with pytest.raises(InvalidSessionTransition):
        recommender.refresh_queue(session_id)
    with pytest.raises(SessionNotFound):
        recommender.refresh_queue(str(uuid.uuid4()))


# --- Playback and the cooldown --------------------------------------------------------------


def test_the_playing_track_is_never_queued_again_while_it_cools_down(unit_of_work, sessions, recommender, listener):
    ids = _add_tracks(unit_of_work, *[(f"a{index}", "ambient", None, f"Artist {index}") for index in range(1, 6)])
    session_id = _start(sessions, listener)
    recommender.refresh_queue(session_id)
    playing = sessions.advance(session_id).playing

    state = recommender.refresh_queue(session_id)

    assert playing.track_id not in {occurrence.track_id for occurrence in state.queue}
    assert state.playing.occurrence_id == playing.occurrence_id
    assert len(state.queue) == 3


def test_a_small_library_keeps_music_flowing(unit_of_work, sessions, recommender, listener):
    ids = _add_tracks(unit_of_work, *[(f"a{index}", "ambient", None, f"Artist {index}") for index in range(1, 5)])
    session_id = _start(sessions, listener)

    played = []
    for _ in range(8):
        state = recommender.refresh_queue(session_id)
        assert len(state.queue) == 3
        played.append(sessions.advance(session_id).playing.track_id)

    # Four equally good tracks rotate; none is held back for good and none alternates with another.
    title_of = {track_id: title for title, track_id in ids.items()}
    assert [title_of[track_id] for track_id in played] == ["a1", "a2", "a3", "a4"] * 2


def test_a_close_more_novel_second_is_queued_to_play_first(unit_of_work, sessions, recommender, listener):
    ids = _add_tracks(
        unit_of_work,
        ("p", "ambient", "calm", "X"),
        ("q1", "ambient", "calm", "Y"),
        ("q2", "ambient", "dark", "Z"),
        ("q3", "ambient", "calm", "W"),
    )
    session_id = _start(sessions, listener)
    recommender.refresh_queue(session_id)
    assert _titles((sessions.advance(session_id).playing,), ids) == ["p"]

    state = recommender.refresh_queue(session_id)

    assert recommender.last_decision.second_plays_first
    assert _titles(state.queue, ids) == ["q2", "q1", "q3"]
    assert [occurrence.rank for occurrence in state.queue] == [2, 1, 3]

    # Once the queue moves on, the surfaced order (#2 before #1) can still be reconstructed.
    sessions.advance(session_id)
    recommender.refresh_queue(session_id)
    surfaced = [occurrence for occurrence in sessions.history(session_id).occurrences if occurrence.surfaced_at == state.queue[0].surfaced_at]
    assert [(occurrence.rank, occurrence.surfaced_position) for occurrence in sorted(surfaced, key=lambda o: o.surfaced_position)] == [(2, 0), (1, 1), (3, 2)]
    assert all(occurrence.queue_position is None for occurrence in surfaced)


# --- Feedback through turns ----------------------------------------------------------------------


def test_not_for_me_keeps_the_track_out_for_the_rest_of_the_session(unit_of_work, sessions, recommender, listener):
    ids = _add_tracks(unit_of_work, *[(f"a{index}", "ambient", None, f"Artist {index}") for index in range(1, 5)], ("r1", "rock", None, "R"))
    session_id = _start(sessions, listener)
    recommender.refresh_queue(session_id)
    rejected = sessions.advance(session_id).playing
    sessions.apply_turn(session_id, TurnKind.NOT_FOR_ME)

    queued = []
    for _ in range(6):
        state = recommender.refresh_queue(session_id)
        queued.extend(occurrence.track_id for occurrence in state.queue)
        sessions.advance(session_id)

    assert rejected.track_id == ids["a1"]
    assert rejected.track_id not in queued
    # Similar tracks lose session fit, but the explicit ambient intent still outranks rock.
    first = recommender.decide(session_id).picks[0]
    assert first.score.session.value == 0.0
    assert first.candidate.music.genre == "ambient"


def test_more_like_this_pulls_tracks_like_it_up(unit_of_work, sessions, recommender, listener):
    ids = _add_tracks(
        unit_of_work,
        ("a1", "ambient", "dark", None),
        ("a2", "ambient", "calm", None),
        ("a3", "ambient", "dark", None),
        ("a4", "ambient", "calm", None),
        ("a5", "ambient", "calm", None),
    )
    session_id = _start(sessions, listener)
    recommender.refresh_queue(session_id)
    sessions.advance(session_id)

    without_feedback = recommender.decide(session_id)
    sessions.apply_turn(session_id, TurnKind.MORE_LIKE_THIS)
    state = recommender.refresh_queue(session_id)

    assert [pick.candidate.music.title for pick in without_feedback.picks] == ["a2", "a3", "a4"]
    assert _titles(state.queue, ids) == ["a3", "a2", "a4"]


# --- Exploration ------------------------------------------------------------------------------------


def _exploration_library(unit_of_work):
    return _add_tracks(
        unit_of_work,
        ("a1", "ambient", "calm", "A"),
        ("a2", "ambient", "calm", "B"),
        ("a3", "ambient", "calm", "C"),
        ("a4", "ambient", "dark", "D"),
        ("a5", "ambient", "calm", "E"),
    )


def test_an_exploration_pick_is_marked_on_its_occurrence(unit_of_work, sessions, explorer, listener):
    ids = _exploration_library(unit_of_work)
    session_id = _start(sessions, listener)

    state = explorer.refresh_queue(session_id)

    assert _titles(state.queue, ids) == ["a1", "a2", "a4"]
    assert [occurrence.is_exploration for occurrence in state.queue] == [False, False, True]
    stored = {occurrence.track_id: occurrence.is_exploration for occurrence in sessions.history(session_id).occurrences}
    assert stored[ids["a4"]] is True


def test_a_preview_does_not_change_what_the_refresh_chooses(unit_of_work, sessions, listener, clock):
    """Seed 31's first draw (0.012) explores and its second (0.112) does not, so a preview that consumed a draw
    would turn the refresh's exploration off. Two fresh sessions over the same library, one previewed first."""
    ids = _exploration_library(unit_of_work)
    direct = RecommendationService(unit_of_work, rng=random.Random(31), clock=clock)
    previewed = RecommendationService(unit_of_work, rng=random.Random(31), clock=clock)
    first = _start(sessions, listener)
    refreshed_directly = direct.refresh_queue(first)
    second = _start(sessions, listener)

    before = previewed._rng.getstate()
    preview = previewed.decide(second)
    assert previewed._rng.getstate() == before
    assert previewed.decide(second) == preview  # previews repeat, because nothing moved
    refreshed_after_preview = previewed.refresh_queue(second)

    surfaced = lambda state: [(occurrence.track_id, occurrence.is_exploration) for occurrence in state.queue]  # noqa: E731
    assert surfaced(refreshed_after_preview) == surfaced(refreshed_directly)
    assert _titles(refreshed_after_preview.queue, ids) == ["a1", "a2", "a4"] and refreshed_after_preview.queue[-1].is_exploration
    assert [(pick.candidate.track_id, pick.is_exploration) for pick in preview.picks] == surfaced(refreshed_after_preview)
    assert previewed._rng.getstate() != before  # the refresh drew


@pytest.mark.parametrize("kind, rate", [(TurnKind.NOT_FOR_ME, 0.05), (TurnKind.MORE_LIKE_THIS, 0.125)])
def test_the_outcome_of_an_exploration_pick_moves_the_rate(unit_of_work, sessions, explorer, listener, kind, rate):
    _exploration_library(unit_of_work)
    session_id = _start(sessions, listener)
    exploration = explorer.refresh_queue(session_id).queue[-1]
    sessions.play(session_id, exploration.occurrence_id)

    sessions.apply_turn(session_id, kind)

    assert explorer.decide(session_id).exploration_rate == pytest.approx(rate)


def _tagged_library(unit_of_work, in_genre_mood=None):
    """Ambient tracks by four artists and one rock track. Optionally a fourth ambient track in another mood."""
    specs = [("a1", "ambient", "calm", "A"), ("a2", "ambient", "calm", "B"), ("a3", "ambient", "calm", "C"), ("r1", "rock", "calm", "R")]
    specs.append(("a4", "ambient", in_genre_mood or "calm", "D"))
    return _add_tracks(unit_of_work, *specs)


# The recommender fixture never explores automatically, so whatever a control does below, it does deterministically.


@pytest.mark.parametrize(
    "control, order", [(TurnKind.TRY_SOMETHING_DIFFERENT, ["r1", "a1", "a2"]), (TurnKind.SURPRISE_ME, ["a1", "a2", "r1"])]
)
def test_a_control_takes_the_next_refresh_outside_the_requested_genre(unit_of_work, sessions, recommender, listener, control, order):
    """Try something different makes r1 the next to play; Surprise me gives it the last slot. Over tags alone,
    nothing about r1 can be compared once the genre is set aside, so it is surfaced without a score."""
    ids = _tagged_library(unit_of_work)
    session_id = _start(sessions, listener)
    before = recommender.refresh_queue(session_id)

    sessions.apply_turn(session_id, control)
    after = recommender.refresh_queue(session_id)

    assert _titles(before.queue, ids) == ["a1", "a2", "a3"]
    assert _titles(after.queue, ids) == order
    explored = after.queue[order.index("r1")]
    assert (explored.is_exploration, explored.score) == (True, None)
    assert all(occurrence.score is not None for occurrence in after.queue if occurrence is not explored)
    assert recommender.last_decision.steering is control


def test_a_control_acts_on_the_next_refresh_only(unit_of_work, sessions, recommender, listener):
    ids = _tagged_library(unit_of_work)
    session_id = _start(sessions, listener)
    sessions.apply_turn(session_id, TurnKind.TRY_SOMETHING_DIFFERENT)

    directed = recommender.refresh_queue(session_id)
    following = recommender.refresh_queue(session_id)

    assert _titles(directed.queue, ids) == ["r1", "a1", "a2"]
    assert _titles(following.queue, ids) == ["a1", "a2", "a3"]
    assert recommender.last_decision.steering is None


def test_deciding_does_not_use_up_a_control(unit_of_work, sessions, recommender, listener):
    _tagged_library(unit_of_work)
    session_id = _start(sessions, listener)
    sessions.apply_turn(session_id, TurnKind.SURPRISE_ME)

    assert recommender.decide(session_id).steering is TurnKind.SURPRISE_ME
    assert recommender.decide(session_id).steering is TurnKind.SURPRISE_ME
    recommender.refresh_queue(session_id)
    assert recommender.decide(session_id).steering is None


def test_surprise_me_keeps_to_the_genre_when_it_offers_novelty(unit_of_work, sessions, recommender, listener):
    ids = _tagged_library(unit_of_work, in_genre_mood="dark")
    session_id = _start(sessions, listener)

    sessions.apply_turn(session_id, TurnKind.SURPRISE_ME)
    state = recommender.refresh_queue(session_id)

    assert _titles(state.queue, ids) == ["a1", "a2", "a4"]
    assert state.queue[-1].is_exploration and state.queue[-1].score is not None
    assert not recommender.last_decision.picks[-1].genre_set_aside


def test_more_familiar_suppresses_exploration_for_the_next_refresh(unit_of_work, sessions, explorer, listener):
    """The explorer fixture explores automatically whenever it can; More familiar stops that once."""
    ids = _tagged_library(unit_of_work, in_genre_mood="dark")
    session_id = _start(sessions, listener)
    sessions.apply_turn(session_id, TurnKind.MORE_FAMILIAR)

    familiar = explorer.refresh_queue(session_id)
    following = explorer.refresh_queue(session_id)

    assert _titles(familiar.queue, ids) == ["a1", "a2", "a3"]
    assert not any(occurrence.is_exploration for occurrence in familiar.queue)
    assert _titles(following.queue, ids) == ["a1", "a2", "a4"]
    assert following.queue[-1].is_exploration


@pytest.mark.parametrize("control", [TurnKind.TRY_SOMETHING_DIFFERENT, TurnKind.SURPRISE_ME, TurnKind.MORE_FAMILIAR])
def test_a_refinement_before_the_refresh_supersedes_the_control(unit_of_work, sessions, explorer, listener, control):
    ids = _tagged_library(unit_of_work, in_genre_mood="dark")
    session_id = _start(sessions, listener)
    sessions.apply_turn(session_id, control)

    sessions.apply_turn(session_id, TurnKind.REFINE, ListeningContext(temporary_genres=("ambient",), activity="reading"))
    state = explorer.refresh_queue(session_id)

    assert explorer.last_decision.steering is None
    assert _titles(state.queue, ids) == ["a1", "a2", "a4"]  # automatic exploration, within the genre


def test_a_newer_control_replaces_a_pending_one(unit_of_work, sessions, recommender, listener):
    ids = _tagged_library(unit_of_work)
    session_id = _start(sessions, listener)
    sessions.apply_turn(session_id, TurnKind.TRY_SOMETHING_DIFFERENT)
    sessions.apply_turn(session_id, TurnKind.MORE_FAMILIAR)

    state = recommender.refresh_queue(session_id)

    assert recommender.last_decision.steering is TurnKind.MORE_FAMILIAR
    assert _titles(state.queue, ids) == ["a1", "a2", "a3"]


def test_a_control_and_its_refresh_are_ordered_even_when_the_clock_stands_still(unit_of_work, listener):
    """This machine's clock moves in about 1 ms steps, so a turn and the refresh after it can read the same
    time. Within a session every change is still strictly later, so the control is acted on exactly once."""
    frozen = lambda: _NOW  # noqa: E731
    sessions = SessionService(unit_of_work, clock=frozen)
    recommender = RecommendationService(unit_of_work, rng=_FixedRandom(0.999), clock=frozen)
    ids = _tagged_library(unit_of_work)
    session_id = _start(sessions, listener)
    recommender.refresh_queue(session_id)

    turn = sessions.apply_turn(session_id, TurnKind.TRY_SOMETHING_DIFFERENT)
    directed = recommender.refresh_queue(session_id)
    following = recommender.refresh_queue(session_id)

    surfaced = sorted({occurrence.surfaced_at for occurrence in sessions.history(session_id).occurrences})
    assert len(surfaced) == 3 and turn.created_at < directed.queue[0].surfaced_at
    assert _titles(directed.queue, ids) == ["r1", "a1", "a2"]
    assert _titles(following.queue, ids) == ["a1", "a2", "a3"]


# --- From session history to policy signals ------------------------------------------------------------


def test_session_signals_read_turns_and_plays_newest_first(unit_of_work, sessions, recommender, listener):
    ids = _exploration_library(unit_of_work)
    session_id = _start(sessions, listener)
    recommender.refresh_queue(session_id)
    first = sessions.advance(session_id).playing
    sessions.apply_turn(session_id, TurnKind.MORE_LIKE_THIS)
    second = sessions.advance(session_id).playing
    sessions.apply_turn(session_id, TurnKind.NOT_FOR_ME)
    third = sessions.get_session(session_id).playing  # Not for me about the playing track moved on (B6)
    sessions.apply_turn(session_id, TurnKind.SURPRISE_ME)

    history = sessions.history(session_id)
    with unit_of_work:
        tracks = {track.track_id: track for track in unit_of_work.tracks.list_all()}
    signals = signals_from_session(history.session, history.turns, history.occurrences, tracks, POLICY_V1)

    assert [(item.track.candidate_id, item.weight) for item in signals.evidence] == [(second.track_id, -1.0), (first.track_id, 1.0)]
    assert signals.excluded_track_ids == {second.track_id}
    assert signals.recent_track_ids == (third.track_id, second.track_id, first.track_id)
    assert signals.last_played.track_id == third.track_id
    assert signals.pending_control is TurnKind.SURPRISE_ME  # no queue surfaced since
    assert signals.context == _AMBIENT
    assert signals.long_term is None
    assert {first.track_id, second.track_id} <= set(ids.values())
