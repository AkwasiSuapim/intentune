"""Feedback Policy v1 domain tests: deterministic, pure, no database (Prototype 1, phase B6).

Execution guide §9 and spec §15, §17: explicit actions (Like, Save, Replay,
Not for me) carry fixed weights; passive playback counts nothing for the first
8 seconds and then by the fraction played; explicit actions take precedence over
passive playback. The boundary tests here are mandatory.

Also covers how a session's turns and raw feedback events become Policy v1
evidence (signals_from_session()): one piece of evidence per occurrence,
recomputed from the raw facts, so different thresholds give a different reading
of the same history.
"""

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.policy import (
    POLICY_V1,
    EvidenceBasis,
    Interpretation,
    RecommendationPolicy,
    event_weight,
    interpret_feedback,
    passive_weight,
    signals_from_session,
)
from src.intentune.domain.session import (
    FeedbackEvent,
    FeedbackEventType,
    OccurrenceStatus,
    RecommendationOccurrence,
    TurnKind,
    new_session,
    new_turn,
)

_NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
_SESSION = new_session(str(uuid.uuid4()), ListeningContext(temporary_genres=("ambient",)), _NOW)
_OCCURRENCE = str(uuid.uuid4())


def _at(seconds):
    return _NOW + timedelta(seconds=seconds)


def _event(event_type, at=1, played=None, duration=None, occurrence_id=_OCCURRENCE):
    return FeedbackEvent(str(uuid.uuid4()), _SESSION.session_id, occurrence_id, event_type, _at(at), played, duration)


def _played(seconds, duration=100.0, at=1, ending=FeedbackEventType.SKIP):
    return _event(ending, at, seconds, duration)


def _turn(kind, at, sequence=2, occurrence_id=_OCCURRENCE):
    return new_turn(_SESSION, sequence, kind, _SESSION.current_context, _at(at), occurrence_id=occurrence_id)


# --- The constants ---------------------------------------------------------------------------


def test_feedback_policy_v1_holds_the_register_weights():
    policy = POLICY_V1

    assert (policy.like_weight, policy.save_weight, policy.replay_weight, policy.not_for_me_weight) == (1.0, 1.0, 1.0, -1.0)
    assert policy.playlist_add_weight == 1.0  # SAVE/PLAYLIST_ADD
    assert (policy.grace_seconds, policy.full_play_weight) == (8.0, 0.80)
    assert policy.passive_bands == ((0.15, -0.50), (0.40, -0.20), (0.75, 0.10), (0.90, 0.50))


@pytest.mark.parametrize(
    "overrides",
    [
        {"grace_seconds": -1.0},
        {"passive_bands": ()},
        {"passive_bands": ((0.40, -0.20), (0.15, -0.50))},
        {"passive_bands": ((0.15, -0.50), (0.15, -0.20))},
        {"passive_bands": ((0.0, -0.50),)},
        {"passive_bands": ((1.5, -0.50),)},
        {"passive_bands": ((0.15, -1.50),)},
        {"full_play_weight": 1.2},
        {"like_weight": -0.1},
        {"replay_weight": 1.1},
        {"not_for_me_weight": 0.2},
    ],
)
def test_feedback_constants_are_validated(overrides):
    with pytest.raises(ValueError):
        RecommendationPolicy(**overrides)


# --- Passive playback: the mandatory boundaries ------------------------------------------------


@pytest.mark.parametrize(
    "played, duration, weight",
    [
        (0.0, 100.0, 0.00),  # nothing played
        (8.0, 100.0, 0.00),  # the grace period includes its last second
        (8.01, 100.0, -0.50),  # just past the grace period, under 15%
        (14.99, 100.0, -0.50),
        (15.0, 100.0, -0.20),  # 15% starts the weak negative band
        (39.99, 100.0, -0.20),
        (40.0, 100.0, 0.10),  # 40% starts the weak positive band
        (74.99, 100.0, 0.10),
        (75.0, 100.0, 0.50),  # 75% starts the medium positive band
        (89.99, 100.0, 0.50),
        (90.0, 100.0, 0.80),  # 90% starts the strong positive band
        (100.0, 100.0, 0.80),
        (130.0, 100.0, 0.80),  # a player clock past the duration caps at 100%
        (30.0, 200.0, -0.20),  # 15% of a longer track
        (8.0, 9.0, 0.00),  # a short track played almost through is still within the grace period
        (9.0, 10.0, 0.80),  # a short track played past the grace period counts by its fraction
    ],
)
def test_passive_playback_counts_by_the_fraction_played_after_the_grace_period(played, duration, weight):
    assert event_weight(_played(played, duration)) == weight
    assert event_weight(_played(played, duration, ending=FeedbackEventType.COMPLETE)) == weight


def test_passive_weight_reads_seconds_for_the_grace_period_and_the_fraction_for_the_bands():
    assert passive_weight(8.0, 0.99) == 0.0
    assert passive_weight(8.5, 0.10) == -0.50
    assert passive_weight(500.0, 0.92) == 0.80


@pytest.mark.parametrize(
    "event_type, weight",
    [
        (FeedbackEventType.LIKE, 1.0),
        (FeedbackEventType.SAVE, 1.0),
        (FeedbackEventType.PLAYLIST_ADD, 1.0),  # B7
        (FeedbackEventType.REPLAY, 1.0),
        (FeedbackEventType.NOT_FOR_ME, -1.0),
    ],
)
def test_explicit_actions_keep_their_weight_whatever_was_played(event_type, weight):
    assert event_weight(_event(event_type)) == weight
    assert event_weight(_event(event_type, played=3.0, duration=200.0)) == weight  # within the grace period


# --- Precedence -----------------------------------------------------------------------------------


def test_with_only_playback_the_latest_playback_event_decides():
    latest = _played(20.0, at=2)
    interpretation = interpret_feedback((), (_played(95.0, at=1), latest))

    assert interpretation == Interpretation(
        weight=-0.20, basis=EvidenceBasis.PASSIVE, at=_at(2), occurrence_id=_OCCURRENCE, event_id=latest.event_id
    )


def test_the_interpretation_names_the_raw_fact_that_decided_it():
    """B10 audit: long-term evidence references the exact event or turn behind each piece of evidence."""
    like, save = _event(FeedbackEventType.LIKE, at=1), _event(FeedbackEventType.SAVE, at=2)
    refusal = _turn(TurnKind.NOT_FOR_ME, at=3)

    by_event = interpret_feedback((), (like, save))
    by_turn = interpret_feedback((refusal,), (like, save))

    assert (by_event.event_id, by_event.turn_id) == (save.event_id, None)
    assert (by_turn.event_id, by_turn.turn_id, by_turn.weight) == (None, refusal.turn_id, -1.0)
    assert interpret_feedback((), ()).event_id is None


def test_playback_within_the_grace_period_is_no_preference_evidence():
    interpretation = interpret_feedback((), (_played(5.0),))

    assert (interpretation.weight, interpretation.basis, interpretation.excluded) == (0.0, EvidenceBasis.GRACE, False)


@pytest.mark.parametrize("passive_first", [True, False])
def test_an_explicit_action_takes_precedence_over_passive_playback(passive_first):
    like_at, skip_at = (2, 1) if passive_first else (1, 2)
    interpretation = interpret_feedback((), (_event(FeedbackEventType.LIKE, like_at), _played(10.0, at=skip_at)))

    assert (interpretation.weight, interpretation.basis, interpretation.at) == (1.0, EvidenceBasis.EXPLICIT, _at(like_at))


def test_not_for_me_outweighs_a_full_play_and_excludes_the_track():
    interpretation = interpret_feedback((), (_played(100.0, ending=FeedbackEventType.COMPLETE, at=2), _event(FeedbackEventType.NOT_FOR_ME, 1)))

    assert (interpretation.weight, interpretation.excluded) == (-1.0, True)


def test_the_latest_explicit_action_decides_the_evidence_but_not_for_me_keeps_the_track_excluded():
    """The evidence follows a listener who changes their mind; the exclusion of D18 lasts the session."""
    rejected_then_liked = interpret_feedback((), (_event(FeedbackEventType.NOT_FOR_ME, 1), _event(FeedbackEventType.LIKE, 2)))
    rejected_then_replayed = interpret_feedback((), (_event(FeedbackEventType.NOT_FOR_ME, 1), _event(FeedbackEventType.REPLAY, 2)))
    liked_then_rejected = interpret_feedback((), (_event(FeedbackEventType.LIKE, 1), _event(FeedbackEventType.NOT_FOR_ME, 2)))
    liked = interpret_feedback((), (_event(FeedbackEventType.LIKE, 1),))

    assert (rejected_then_liked.weight, rejected_then_liked.excluded) == (1.0, True)
    assert (rejected_then_replayed.weight, rejected_then_replayed.excluded) == (1.0, True)
    assert (liked_then_rejected.weight, liked_then_rejected.excluded) == (-1.0, True)
    assert (liked.weight, liked.excluded) == (1.0, False)


def test_a_not_for_me_turn_excludes_as_an_event_does():
    turn_then_liked = interpret_feedback((_turn(TurnKind.NOT_FOR_ME, 1),), (_event(FeedbackEventType.LIKE, 2),))

    assert (turn_then_liked.weight, turn_then_liked.excluded) == (1.0, True)


def test_turns_and_events_are_read_together():
    """More like this is as strong as Like; a Not for me turn and event about one occurrence are one rejection."""
    more_like_this = interpret_feedback((_turn(TurnKind.MORE_LIKE_THIS, 3),), (_played(10.0, at=1),))
    rejected_twice = interpret_feedback((_turn(TurnKind.NOT_FOR_ME, 1),), (_event(FeedbackEventType.NOT_FOR_ME, 2),))
    steering_only = interpret_feedback((_turn(TurnKind.NEXT, 1),), ())

    assert (more_like_this.weight, more_like_this.basis) == (1.0, EvidenceBasis.EXPLICIT)
    assert (rejected_twice.weight, rejected_twice.excluded, rejected_twice.at) == (-1.0, True, _at(2))
    assert steering_only == Interpretation(weight=0.0, basis=EvidenceBasis.NONE)


def test_nothing_said_or_played_is_no_evidence():
    assert interpret_feedback((), ()) == Interpretation(weight=0.0, basis=EvidenceBasis.NONE)


# --- Unlike (B9) ----------------------------------------------------------------------------


def test_an_unlike_is_neutral_on_its_own():
    unlike = _event(FeedbackEventType.UNLIKE)

    assert event_weight(unlike) == 0.0
    assert interpret_feedback((), (unlike,)) == Interpretation(weight=0.0, basis=EvidenceBasis.NONE)


def test_an_unlike_takes_back_the_like_and_leaves_no_positive_evidence():
    taken_back = interpret_feedback((), (_event(FeedbackEventType.LIKE, 1), _event(FeedbackEventType.UNLIKE, 2)))

    assert taken_back == Interpretation(weight=0.0, basis=EvidenceBasis.NONE)


def test_after_an_unlike_the_rest_of_the_evidence_decides_as_if_the_like_had_not_been_given():
    played_then_taken_back = interpret_feedback(
        (), (_played(10.0, at=1), _event(FeedbackEventType.LIKE, 2), _event(FeedbackEventType.UNLIKE, 3))
    )
    saved_then_taken_back = interpret_feedback(
        (), (_event(FeedbackEventType.SAVE, 1), _event(FeedbackEventType.LIKE, 2), _event(FeedbackEventType.UNLIKE, 3))
    )
    more_like_this_kept = interpret_feedback(
        (_turn(TurnKind.MORE_LIKE_THIS, 1),), (_event(FeedbackEventType.LIKE, 2), _event(FeedbackEventType.UNLIKE, 3))
    )

    assert (played_then_taken_back.weight, played_then_taken_back.basis, played_then_taken_back.at) == (-0.5, EvidenceBasis.PASSIVE, _at(1))
    assert (saved_then_taken_back.weight, saved_then_taken_back.at) == (1.0, _at(1))  # an Unlike takes back only a Like
    assert (more_like_this_kept.weight, more_like_this_kept.at) == (1.0, _at(1))


def test_a_like_after_an_unlike_counts_again():
    liked_again = interpret_feedback(
        (), (_event(FeedbackEventType.LIKE, 1), _event(FeedbackEventType.UNLIKE, 2), _event(FeedbackEventType.LIKE, 3))
    )

    assert (liked_again.weight, liked_again.basis, liked_again.at) == (1.0, EvidenceBasis.EXPLICIT, _at(3))


def test_an_unlike_is_never_a_rejection_and_never_lifts_one():
    unliked = interpret_feedback((), (_event(FeedbackEventType.LIKE, 1), _event(FeedbackEventType.UNLIKE, 2)))
    refused_then_liked_then_unliked = interpret_feedback(
        (), (_event(FeedbackEventType.NOT_FOR_ME, 1), _event(FeedbackEventType.LIKE, 2), _event(FeedbackEventType.UNLIKE, 3))
    )

    assert unliked.excluded is False and unliked.weight == 0.0
    assert refused_then_liked_then_unliked.excluded is True  # D18: the exclusion stays
    assert (refused_then_liked_then_unliked.weight, refused_then_liked_then_unliked.at) == (-1.0, _at(1))


def test_an_unlike_takes_back_a_like_given_on_another_occurrence_of_the_track():
    """Evidence is per track in the session (B6), so a Like on the queued card is taken back from the playing one."""
    queued, playing = str(uuid.uuid4()), str(uuid.uuid4())

    interpretation = interpret_feedback(
        (), (_event(FeedbackEventType.LIKE, 1, occurrence_id=queued), _event(FeedbackEventType.UNLIKE, 2, occurrence_id=playing))
    )

    assert interpretation.weight == 0.0


# --- From raw history to session evidence -------------------------------------------------------


def _track(char, genre):
    return Track(
        track_id=str(uuid.uuid4()), sha256=char * 64, size_bytes=10, audio_format=AudioFormat.FLAC, status=TrackStatus.READY,
        original_filename=f"{char}.flac", created_at=_NOW, updated_at=_NOW, analysis_version="test@1",
        labels=(TrackLabel(LabelKind.GENRE, genre, "tag", True),),
    )


def _played_occurrence(track, position, exploration=False):
    return RecommendationOccurrence(
        occurrence_id=str(uuid.uuid4()), session_id=_SESSION.session_id, track_id=track.track_id, rank=position + 1,
        algorithm="policy-v1", status=OccurrenceStatus.PLAYED, surfaced_at=_NOW, updated_at=_at(position + 1),
        surfaced_position=position, started_at=_at(position + 1), finished_at=_at(position + 2), is_exploration=exploration,
    )


@pytest.fixture
def history():
    tracks = [_track(char, genre) for char, genre in (("a", "ambient"), ("b", "rock"), ("c", "jazz"), ("d", "folk"))]
    occurrences = [_played_occurrence(track, position, exploration=position == 3) for position, track in enumerate(tracks)]
    return {track.track_id: track for track in tracks}, occurrences


def _signals(history, turns=(), events=(), policy=POLICY_V1):
    tracks, occurrences = history
    return signals_from_session(_SESSION, list(turns), occurrences, tracks, policy, feedback_events=list(events))


def _about(occurrence, event_type, at, played=None, duration=None):
    return _event(event_type, at, played, duration, occurrence_id=occurrence.occurrence_id)


def test_each_occurrence_gives_one_piece_of_evidence_newest_first(history):
    _, (ambient, rock, jazz, _) = history
    events = [
        _about(ambient, FeedbackEventType.LIKE, 10),
        _about(ambient, FeedbackEventType.LIKE, 11),  # a second Like is not more evidence
        _about(rock, FeedbackEventType.SKIP, 13, played=10.0, duration=100.0),
        _about(jazz, FeedbackEventType.COMPLETE, 14, played=4.0, duration=4.5),
    ]

    signals = _signals(history, events=events)

    # jazz played 4 of 4.5 seconds: within the grace period, so no evidence.
    assert [(item.track.candidate_id, item.weight) for item in signals.evidence] == [(rock.track_id, -0.50), (ambient.track_id, 1.0)]
    assert signals.excluded_track_ids == frozenset()


def _later_occurrence(earlier, status=OccurrenceStatus.PLAYED, exploration=False):
    """Another occurrence of the same track, as a refresh or a second play would create."""
    played = status is OccurrenceStatus.PLAYED
    return RecommendationOccurrence(
        occurrence_id=str(uuid.uuid4()), session_id=_SESSION.session_id, track_id=earlier.track_id, rank=1, algorithm="policy-v1",
        status=status, surfaced_at=_at(20), updated_at=_at(21), surfaced_position=0,
        started_at=_at(21) if played else None, finished_at=_at(22), is_exploration=exploration,
    )


def test_a_like_on_the_queued_card_still_decides_when_the_track_plays_after_a_refresh(history):
    """The refresh after the Like surfaced the track again as a new occurrence; the skip is about the same listening."""
    tracks, occurrences = history
    liked_card = replace(occurrences[0], status=OccurrenceStatus.REPLACED, started_at=None)
    played = _later_occurrence(liked_card)
    events = [_about(liked_card, FeedbackEventType.LIKE, 10), _about(played, FeedbackEventType.SKIP, 30, played=10.0, duration=100.0)]

    signals = signals_from_session(_SESSION, [], [liked_card, played, *occurrences[1:]], tracks, feedback_events=events)

    assert [(item.track.candidate_id, item.weight) for item in signals.evidence] == [(liked_card.track_id, 1.0)]


def test_a_track_heard_twice_in_a_session_is_one_piece_of_evidence(history):
    tracks, occurrences = history
    first = occurrences[1]
    again = _later_occurrence(first)
    events = [_about(first, FeedbackEventType.COMPLETE, 10, played=100.0, duration=100.0), _about(again, FeedbackEventType.SKIP, 30, played=10.0, duration=100.0)]

    signals = signals_from_session(_SESSION, [], [*occurrences, again], tracks, feedback_events=events)

    assert [(item.track.candidate_id, item.weight) for item in signals.evidence] == [(first.track_id, -0.50)]


def test_an_exploration_outcome_follows_the_occurrence_the_deciding_signal_was_about(history):
    tracks, occurrences = history
    explored = occurrences[3]  # surfaced as an exploration pick
    heard_again = _later_occurrence(explored)
    events = [_about(explored, FeedbackEventType.SKIP, 10, played=10.0, duration=100.0), _about(heard_again, FeedbackEventType.COMPLETE, 30, played=100.0, duration=100.0)]

    [evidence] = signals_from_session(_SESSION, [], [*occurrences, heard_again], tracks, feedback_events=events).evidence

    assert (evidence.weight, evidence.is_exploration) == (0.80, False)


def test_not_for_me_as_an_event_excludes_the_track_for_the_session(history):
    _, (ambient, *_) = history

    signals = _signals(history, events=[_about(ambient, FeedbackEventType.NOT_FOR_ME, 10)])

    assert signals.excluded_track_ids == {ambient.track_id}
    assert [(item.track.candidate_id, item.weight) for item in signals.evidence] == [(ambient.track_id, -1.0)]


def test_changing_ones_mind_changes_the_evidence_but_not_the_exclusion(history):
    """After Not for me, a Replay makes the track positive evidence for similar tracks; the track itself stays out (D18)."""
    _, (ambient, *_) = history
    events = [_about(ambient, FeedbackEventType.NOT_FOR_ME, 10), _about(ambient, FeedbackEventType.REPLAY, 11)]

    signals = _signals(history, events=events)

    assert signals.excluded_track_ids == {ambient.track_id}
    assert [(item.track.candidate_id, item.weight) for item in signals.evidence] == [(ambient.track_id, 1.0)]


def test_an_exploration_picks_playback_is_an_exploration_outcome(history):
    _, (*_, folk) = history
    skip = _about(folk, FeedbackEventType.SKIP, 10, played=10.0, duration=100.0)

    [evidence] = _signals(history, events=[skip]).evidence

    assert (evidence.weight, evidence.is_exploration) == (-0.50, True)


def test_the_raw_facts_can_be_read_again_with_other_thresholds(history):
    """Raw playback facts are stored, not interpreted weights, so a later policy reads the same history differently."""
    _, (ambient, *_) = history
    skip = _about(ambient, FeedbackEventType.SKIP, 10, played=12.0, duration=100.0)

    v1 = _signals(history, events=[skip])
    longer_grace = _signals(history, events=[skip], policy=RecommendationPolicy(version="policy-test", grace_seconds=15.0))

    assert [item.weight for item in v1.evidence] == [-0.50]
    assert longer_grace.evidence == ()


def test_feedback_about_an_occurrence_outside_the_history_is_ignored(history):
    stray = _event(FeedbackEventType.LIKE, 10, occurrence_id=str(uuid.uuid4()))

    assert _signals(history, events=[stray]).evidence == ()
