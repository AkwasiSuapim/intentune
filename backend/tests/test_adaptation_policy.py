"""Long-Term Adaptation Policy v1 (Prototype 1, phase B10): the gate, consistency, bounds, and recomputation. Pure.

Evidence items are built here directly, with whatever features a test needs.
No library track has energy or any other measured feature yet (no pipeline
provides them), so numeric adaptation can only be exercised on synthetic
candidates. The feedback semantics, through the real use cases and storage,
are in test_long_term_adaptation_service.py.
"""

import itertools
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.intentune.domain.adaptation import (
    ADAPTATION_V1,
    AdaptationPolicy,
    AdjustmentCause,
    AdjustmentChange,
    EvidenceReference,
    LongTermEvidence,
    ProfileAdjustment,
    ProfileDimension,
    derive_profile,
    plan_adjustments,
)
from src.intentune.domain.models import MusicCandidate, UserProfile
from src.intentune.domain.policy import EvidenceBasis, Interpretation

_T0 = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
_S1, _S2, _S3 = (str(uuid.uuid4()) for _ in range(3))
_minutes = itertools.count()


def _item(session, weight=1.0, track=None, **features):
    """One strong effective item about a track (a fresh one unless given) with these features, a minute after the last."""
    track_id = track or str(uuid.uuid4())
    return LongTermEvidence(
        session_id=session,
        track_id=track_id,
        weight=weight,
        at=_T0 + timedelta(minutes=next(_minutes)),
        music=MusicCandidate(candidate_id=track_id, title="t", creator="c", source="local", **features),
        feedback_event_id=str(uuid.uuid4()),
    )


def _likes(sessions, **features):
    """One positive item per listed session, all with these features."""
    return [_item(session, **features) for session in sessions]


# --- What is strong -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "interpretation, polarity",
    [
        (Interpretation(1.0, EvidenceBasis.EXPLICIT), 1),  # Like, Save, Playlist add, Replay, More like this
        (Interpretation(-1.0, EvidenceBasis.EXPLICIT), -1),  # Not for me
        (Interpretation(0.80, EvidenceBasis.PASSIVE), 1),  # 90-100% completion
        (Interpretation(0.50, EvidenceBasis.PASSIVE), 0),  # 75-89%: medium, not strong
        (Interpretation(0.10, EvidenceBasis.PASSIVE), 0),
        (Interpretation(-0.20, EvidenceBasis.PASSIVE), 0),  # a skip is never permanent evidence
        (Interpretation(-0.50, EvidenceBasis.PASSIVE), 0),
        (Interpretation(0.0, EvidenceBasis.GRACE), 0),
        (Interpretation(0.0, EvidenceBasis.NONE), 0),  # an Unlike that took the only Like back
    ],
    ids=["explicit-positive", "not-for-me", "full-play", "medium-play", "weak-play", "weak-skip", "early-skip", "grace", "nothing"],
)
def test_only_full_strength_explicit_actions_and_full_plays_are_strong(interpretation, polarity):
    assert ADAPTATION_V1.polarity(interpretation) == polarity


# --- The gate (categorical) -------------------------------------------------------------------------------


@pytest.mark.parametrize("count", [1, 2, 3])
def test_fewer_than_four_strong_signals_change_nothing(count):
    evidence = _likes([_S1, _S2, _S1][:count], genre="Afrobeats")

    assert derive_profile(evidence).profile == UserProfile()
    assert plan_adjustments(None, derive_profile(evidence)) == ()


def test_four_strong_signals_in_one_session_change_nothing():
    assert derive_profile(_likes([_S1] * 6, genre="Afrobeats")).profile.preferred_genres == ()


def test_four_consistent_strong_signals_across_two_sessions_make_one_bounded_adjustment():
    evidence = _likes([_S1, _S1, _S2, _S2], genre="Afrobeats")

    derived = derive_profile(evidence)
    [plan] = plan_adjustments(None, derived)

    assert derived.profile == UserProfile(preferred_genres=("Afrobeats",))
    assert (plan.dimension, plan.change, plan.cause, plan.subject) == (ProfileDimension.GENRE, AdjustmentChange.ADDED, AdjustmentCause.GATE_MET, "Afrobeats")
    assert (plan.previous, plan.resulting) == ((), ("Afrobeats",))
    assert plan.evidence == tuple(evidence)  # exactly the four items, oldest first
    assert "net 4 (needs 4)" in plan.reason and "2 session(s) (needs 2)" in plan.reason


def test_signals_for_different_values_are_never_pooled():
    evidence = _likes([_S1, _S2], genre="Afrobeats") + _likes([_S1, _S2], genre="Jazz")

    assert derive_profile(evidence).profile.preferred_genres == ()


def test_contrary_strong_evidence_offsets_consistent_evidence():
    four_and_a_refusal = _likes([_S1, _S1, _S2, _S2], genre="Afrobeats") + [_item(_S2, weight=-1.0, genre="Afrobeats")]

    assert derive_profile(four_and_a_refusal).profile.preferred_genres == ()  # net 3
    five = four_and_a_refusal + [_item(_S3, genre="Afrobeats")]
    [plan] = plan_adjustments(None, derive_profile(five))
    assert plan.subject == "Afrobeats" and len(plan.evidence) == 6  # the refusal is part of the record


def test_rejections_alone_never_create_a_preference_or_an_aversion():
    """The profile has no way to express an aversion, so negative evidence only offsets positive evidence."""
    assert derive_profile([_item(session, weight=-1.0, genre="Jazz") for session in (_S1, _S1, _S2, _S2, _S3)]).profile == UserProfile()


def test_values_are_compared_as_policy_v1_compares_labels_and_keep_their_first_spelling():
    evidence = [_item(_S1, genre="Afrobeats"), _item(_S1, genre=" afrobeats"), _item(_S2, genre="AFROBEATS"), _item(_S2, genre="afrobeats ")]

    assert derive_profile(evidence).profile.preferred_genres == ("Afrobeats",)


def test_at_most_three_values_are_kept_the_best_supported():
    evidence = []
    for genre, count in (("Afrobeats", 6), ("Jazz", 5), ("Ambient", 4), ("Rock", 4)):
        evidence += _likes([_S1, _S2] * (count // 2) + [_S3] * (count % 2), genre=genre)

    profile = derive_profile(evidence).profile

    assert profile.preferred_genres == ("Afrobeats", "Jazz", "Rock")  # Ambient and Rock tie on net 4; Rock's evidence is newer


def test_one_track_alone_never_generalizes_into_a_genre_preference():
    """Four strong items across four sessions, all about Song A: still no Afrobeats preference (min_distinct_tracks)."""
    song_a = str(uuid.uuid4())
    evidence = [_item(session, track=song_a, genre="Afrobeats") for session in (_S1, _S2, _S3, str(uuid.uuid4()))]

    assert derive_profile(evidence).profile.preferred_genres == ()
    [support] = derive_profile(evidence).support[ProfileDimension.GENRE]
    assert (support.net, support.sessions, support.tracks) == (4, 4, 1)


def test_a_second_distinct_track_lets_the_gate_pass():
    song_a = str(uuid.uuid4())
    evidence = [_item(session, track=song_a, genre="Afrobeats") for session in (_S1, _S2, _S3)] + [_item(_S3, genre="Afrobeats")]

    [plan] = plan_adjustments(None, derive_profile(evidence))

    assert plan.subject == "Afrobeats"
    assert "about 2 track(s) (needs 2)" in plan.reason


def test_one_track_alone_never_sets_a_numeric_preference_either():
    song_a = str(uuid.uuid4())
    one_track = [_item(session, track=song_a, energy=0.6) for session in (_S1, _S1, _S2, _S2)]  # say, Replay in two sessions

    assert derive_profile(one_track).profile.preferred_energy is None
    with_another = one_track + [_item(_S2, energy=0.62)]
    assert derive_profile(with_another).profile.preferred_energy == 0.6


def test_moods_follow_the_same_gate_including_library_moods():
    assert derive_profile(_likes([_S1, _S1, _S2, _S2], mood="Dreamy")).profile.preferred_moods == ("Dreamy",)


# --- Numeric features ------------------------------------------------------------------------------------------


def test_a_coherent_batch_establishes_a_numeric_preference_at_its_median():
    evidence = [_item(_S1, energy=0.6), _item(_S1, energy=0.7), _item(_S2, energy=0.65), _item(_S2, energy=0.75)]

    derived = derive_profile(evidence)
    [plan] = plan_adjustments(None, derived)

    assert derived.profile.preferred_energy == 0.675
    assert (plan.dimension, plan.change, plan.cause, plan.previous, plan.resulting) == (
        ProfileDimension.ENERGY, AdjustmentChange.SET, AdjustmentCause.GATE_MET, None, 0.675
    )
    assert plan.evidence == tuple(evidence)


@pytest.mark.parametrize(
    "energies, sessions",
    [((0.6, 0.7, 0.65), (_S1, _S2, _S2)), ((0.6, 0.7, 0.65, 0.75), (_S1,) * 4), ((0.2, 0.8, 0.3, 0.9), (_S1, _S1, _S2, _S2))],
    ids=["three", "one-session", "incoherent"],
)
def test_too_few_too_concentrated_or_incoherent_values_change_nothing(energies, sessions):
    evidence = [_item(session, energy=energy) for session, energy in zip(sessions, energies)]

    assert derive_profile(evidence).profile.preferred_energy is None


def test_a_later_batch_moves_a_preference_by_at_most_one_step_and_then_needs_new_evidence():
    first = [_item(session, energy=0.4) for session in (_S1, _S1, _S2, _S2)]
    second = [_item(session, energy=0.9) for session in (_S2, _S3, _S3, _S3)]

    established = derive_profile(first).profile
    moved = derive_profile(first + second)
    plans = plan_adjustments(established, moved)

    assert (established.preferred_energy, moved.profile.preferred_energy) == (0.4, 0.45)  # toward 0.9, but only 0.05
    assert [(plan.change, plan.cause, plan.previous, plan.resulting) for plan in plans] == [
        (AdjustmentChange.RAISED, AdjustmentCause.BOUNDED_STEP, 0.4, 0.45)
    ]
    assert plans[0].evidence == tuple(second)
    # Old evidence is consumed: rereading the same history moves nothing further, however often.
    assert derive_profile(first + second).profile.preferred_energy == 0.45
    assert plan_adjustments(moved.profile, derive_profile(first + second)) == ()
    assert derive_profile(first + second + [_item(_S3, energy=0.9)] * 1).profile.preferred_energy == 0.45  # one new item is not a batch


def test_a_coherent_batch_of_rejections_moves_a_preference_away_but_cannot_set_one():
    liked = [_item(session, energy=0.6) for session in (_S1, _S1, _S2, _S2)]
    refused = [_item(session, weight=-1.0, energy=energy) for session, energy in zip((_S2, _S3, _S3, _S3), (0.85, 0.9, 0.95, 0.9))]

    assert derive_profile(refused).profile.preferred_energy is None
    derived = derive_profile(liked + refused)
    assert derived.profile.preferred_energy == 0.55  # away from 0.9, by one step
    assert [round_.polarity for round_ in derived.rounds[ProfileDimension.ENERGY]] == [1, -1]


def test_tempo_uses_its_own_span_and_step():
    evidence = [_item(session, tempo_bpm=bpm) for session, bpm in zip((_S1, _S1, _S2, _S2), (118.0, 122.0, 120.0, 126.0))]
    faster = [_item(session, tempo_bpm=160.0) for session in (_S2, _S3, _S3, _S3)]

    assert derive_profile(evidence).profile.preferred_tempo_bpm == 121.0
    assert derive_profile(evidence + faster).profile.preferred_tempo_bpm == 126.0  # 5 BPM at most


def test_a_change_of_direction_breaks_a_run_so_mixed_evidence_is_not_a_batch():
    evidence = [_item(_S1, energy=0.6), _item(_S1, energy=0.6), _item(_S2, weight=-1.0, energy=0.6), _item(_S2, energy=0.6), _item(_S2, energy=0.6)]

    assert derive_profile(evidence).profile.preferred_energy is None  # the newest run holds two items


def test_missing_features_are_never_inferred():
    """D21: liked genre-only tracks are genre evidence and nothing else."""
    evidence = _likes([_S1, _S1, _S2, _S2], genre="Afrobeats") + [_item(_S2, energy=0.5)]

    profile = derive_profile(evidence).profile

    assert profile == UserProfile(preferred_genres=("Afrobeats",))
    for field in ("preferred_moods", "preferred_energy", "preferred_danceability", "preferred_tempo_bpm", "preferred_valence", "preferred_acousticness"):
        assert getattr(profile, field) in ((), None)


# --- Recomputation -----------------------------------------------------------------------------------------------


def test_the_same_evidence_always_derives_the_same_profile_in_any_order():
    evidence = (
        _likes([_S1, _S1, _S2, _S2], genre="Afrobeats")
        + [_item(session, energy=energy) for session, energy in zip((_S1, _S1, _S2, _S3), (0.6, 0.7, 0.62, 0.66))]
    )
    shuffled = list(evidence)
    random.Random(7).shuffle(shuffled)

    assert derive_profile(evidence) == derive_profile(shuffled) == derive_profile(tuple(evidence))


def test_withdrawn_evidence_takes_its_change_back_as_a_recorded_adjustment():
    evidence = _likes([_S1, _S1, _S2, _S2], genre="Afrobeats")
    stored = derive_profile(evidence).profile

    [plan] = plan_adjustments(stored, derive_profile(evidence[1:]))  # say an Unlike took the first Like back

    assert (plan.change, plan.cause, plan.subject, plan.previous, plan.resulting) == (
        AdjustmentChange.REMOVED, AdjustmentCause.GATE_LOST, "Afrobeats", ("Afrobeats",), ()
    )
    assert plan.evidence == tuple(evidence[1:])  # what remains, so the record shows why it fell short


def test_a_value_displaced_from_the_bounded_list_says_so():
    stored = UserProfile(preferred_genres=("Ambient", "Jazz", "Rock"))
    evidence = []
    for genre, count in (("Afrobeats", 6), ("Jazz", 5), ("Rock", 5), ("Ambient", 4)):
        evidence += _likes([_S1, _S2] * (count // 2) + [_S3] * (count % 2), genre=genre)

    plans = plan_adjustments(stored, derive_profile(evidence))

    assert [(plan.change, plan.cause, plan.subject) for plan in plans] == [
        (AdjustmentChange.REMOVED, AdjustmentCause.DISPLACED, "Ambient"),
        (AdjustmentChange.ADDED, AdjustmentCause.GATE_MET, "Afrobeats"),
    ]
    assert plans[-1].resulting == ("Afrobeats", "Jazz", "Rock")


def test_numeric_history_since_the_stored_value_is_recorded_batch_by_batch():
    first = [_item(session, energy=0.4) for session in (_S1, _S1, _S2, _S2)]
    second = [_item(session, energy=0.9) for session in (_S2, _S3, _S3, _S3)]

    plans = plan_adjustments(None, derive_profile(first + second))

    assert [(plan.change, plan.previous, plan.resulting) for plan in plans] == [(AdjustmentChange.SET, None, 0.4), (AdjustmentChange.RAISED, 0.4, 0.45)]


def test_a_stored_value_the_new_derivation_never_reaches_is_recomputed_honestly():
    first = [_item(session, energy=0.4) for session in (_S1, _S1, _S2, _S2)]
    second = [_item(session, energy=0.9) for session in (_S2, _S3, _S3, _S3)]
    stored = derive_profile(first + second).profile  # 0.45

    [plan] = plan_adjustments(stored, derive_profile(first[1:] + second))  # one early item withdrawn

    # Without the first batch, the later one is the first to meet the gate, so it establishes the preference at its
    # own median. Bounds apply along the derivation; a withdrawal resets to what the remaining evidence supports.
    assert (plan.change, plan.cause, plan.previous, plan.resulting) == (AdjustmentChange.RAISED, AdjustmentCause.RECOMPUTED, 0.45, 0.9)
    assert plan.reason.startswith("recomputed energy from the current evidence (0.45 to 0.9)")
    assert [(cleared.change, cleared.resulting) for cleared in plan_adjustments(stored, derive_profile([]))] == [(AdjustmentChange.CLEARED, None)]


# --- Values that hold together ----------------------------------------------------------------------------------


def test_policy_constants_are_validated():
    for invalid in ({"version": " "}, {"min_strong_signals": 0}, {"min_sessions": 0}, {"min_distinct_tracks": 0}, {"min_strong_passive_weight": 0.0},
                    {"max_unit_step": 1.5}, {"tempo_coherence_span_bpm": 0.0}, {"max_preferred_values": 0}):
        with pytest.raises(ValueError):
            AdaptationPolicy(**invalid)


def test_evidence_and_adjustments_rest_on_exactly_one_raw_fact_and_name_categorical_values():
    session, track, event, turn = (str(uuid.uuid4()) for _ in range(4))
    music = MusicCandidate(candidate_id=track, title="t", creator="c", source="local")
    with pytest.raises(ValueError):
        LongTermEvidence(session, track, 1.0, _T0, music)  # no raw fact
    with pytest.raises(ValueError):
        LongTermEvidence(session, track, 1.0, _T0, music, feedback_event_id=event, session_turn_id=turn)
    with pytest.raises(ValueError):
        EvidenceReference(session, track, 0.0, feedback_event_id=event)
    adjustment = dict(
        adjustment_id=str(uuid.uuid4()), listener_profile_id=str(uuid.uuid4()), sequence=1, dimension=ProfileDimension.GENRE,
        change=AdjustmentChange.ADDED, cause=AdjustmentCause.GATE_MET, subject="Jazz", previous=(), resulting=("Jazz",),
        reason="meets the gate", policy_version="adaptation-v1", created_at=_T0,
    )
    assert ProfileAdjustment(**adjustment).resulting == ("Jazz",)
    for invalid in ({"subject": None}, {"sequence": 0}, {"dimension": ProfileDimension.ENERGY}):
        with pytest.raises(ValueError):
            ProfileAdjustment(**{**adjustment, **invalid})
