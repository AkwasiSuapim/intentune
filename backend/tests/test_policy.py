"""Recommendation Policy v1 domain tests: deterministic, pure, no database (Prototype 1, phase B5).

Covers the B5 acceptance scenarios of the execution guide (§8): no feedback,
positive feedback, early skip, Not for me, current intent conflicting with
history, missing features, a finite library, exploration success and
failure, and the #2 safety threshold. Also covers each stage on its own:
feature fit and its reuse of the legacy scoring primitives, similarity,
session fit, the combined score, diversity, and the policy's constants.

Randomness only decides whether to explore; tests fix it with _FixedRandom.
"""

import random
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.intentune.adapters.csv_catalog import load_music_candidates
from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.domain.models import ListeningContext, MusicCandidate, UserProfile
from src.intentune.domain.policy import (
    POLICY_V1,
    PolicyCandidate,
    RecommendationPolicy,
    SessionEvidence,
    SessionSignals,
    Targets,
    candidate_from_track,
    candidate_similarity,
    cooldown_window,
    decide,
    exploration_rate,
    feature_fit,
    score,
    session_fit,
)
from src.intentune.domain.scoring import DANCEABILITY_WEIGHT, ENERGY_WEIGHT, GENRE_WEIGHT, MOOD_WEIGHT, score_candidate
from src.intentune.domain.session import TurnKind

_AMBIENT = ListeningContext(temporary_genres=("ambient",))
_MID_ENERGY = ListeningContext(target_energy=0.5)
# Without a long-term profile, the intent and session weights are renormalized over .85.
_INTENT_SHARE = 0.55 / 0.85
_SESSION_SHARE = 0.30 / 0.85


class _FixedRandom(random.Random):
    """A Random whose random() always returns one value, so exploration is decided by the test."""

    def __init__(self, value):
        super().__init__(0)
        self.value = value

    def random(self):
        return self.value


def _never_explore():
    return _FixedRandom(0.999)


def _always_explore():
    return _FixedRandom(0.0)


def _music(track_id, **features):
    return MusicCandidate(candidate_id=track_id, title=track_id, creator="Someone", source="local", **features)


def _candidate(track_id, artist=None, available=True, **features):
    return PolicyCandidate(music=_music(track_id, **features), artist=artist, available=available)


def _ids(decision):
    return [pick.candidate.track_id for pick in decision.picks]


def _pick(decision, track_id):
    return next(pick for pick in decision.picks if pick.candidate.track_id == track_id)


def _combined(intent, session=0.5):
    return _INTENT_SHARE * intent + _SESSION_SHARE * session


# --- The policy's constants ---------------------------------------------------------------


def test_policy_v1_holds_the_spec_constants_under_one_version():
    policy = POLICY_V1

    assert policy.version == "policy-v1"
    assert (policy.intent_weight, policy.session_weight, policy.long_term_weight) == (0.55, 0.30, 0.15)
    assert (policy.neutral_session_fit, policy.recency_decay, policy.not_for_me_weight) == (0.5, 0.85, -1.0)
    assert (policy.exploration_rate, policy.swap_margin, policy.queue_size) == (0.10, 0.08, 3)


def test_policy_v1_feature_weights_keep_the_legacy_proportions():
    weights = POLICY_V1.feature_weights

    assert (weights.genre, weights.mood, weights.energy, weights.danceability) == (
        GENRE_WEIGHT, MOOD_WEIGHT, ENERGY_WEIGHT, DANCEABILITY_WEIGHT
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": " "},
        {"queue_size": 0},
        {"cooldown_plays": -1},
        {"intent_weight": 0.6},
        {"intent_weight": 0.70, "session_weight": 0.45, "long_term_weight": -0.15},
        {"exploration_rate": 1.5},
        {"swap_margin": -0.01},
        {"not_for_me_weight": 0.5},
        {"more_like_this_weight": -0.5},
        {"tempo_scale_bpm": 0.0},
        {"near_duplicate_min_features": 0},
        {"exploration_failure_factor": -1.0},
        {"recent_play_penalty": 1.5},
        {"artist_repeat_penalty": -0.1},
    ],
)
def test_policy_rejects_invalid_constants(overrides):
    with pytest.raises(ValueError):
        RecommendationPolicy(**overrides)


# --- Intent fit reuses the legacy scoring ------------------------------------------------------


@pytest.mark.parametrize(
    "profile",
    [
        UserProfile(preferred_genres=("pop",), preferred_moods=("happy",), preferred_energy=0.8, preferred_danceability=0.8),
        UserProfile(preferred_genres=("lofi",), preferred_moods=("chill",), preferred_energy=0.4, preferred_danceability=0.6),
        UserProfile(preferred_genres=("rock", "metal"), preferred_moods=("intense",), preferred_energy=0.95, preferred_danceability=0.3),
    ],
)
def test_intent_fit_equals_legacy_scoring_for_complete_inputs(profile):
    """The policy scores features with the legacy primitives, so the four-feature results are identical."""
    songs = load_music_candidates("data/songs.csv")
    assert songs

    for song in songs:
        fit = feature_fit(song, Targets.from_profile(profile))
        legacy = score_candidate(song, profile)
        assert fit.value == pytest.approx(legacy.total_score / legacy.maximum_score, abs=1e-6)
        assert [feature.feature for feature in fit.features] == [component.feature_name for component in legacy.components]


# --- Feature fit and missing features ---------------------------------------------------------


def test_feature_fit_compares_only_features_both_sides_have():
    fit = feature_fit(_music("a", genre="ambient"), Targets(genres=("ambient",), energy=0.2))

    assert fit.value == 1.0
    assert [feature.feature for feature in fit.features] == ["genre"]


def test_feature_fit_is_unavailable_when_nothing_can_be_compared():
    assert feature_fit(_music("a", genre="ambient"), Targets(energy=0.2)) is None
    assert feature_fit(_music("a"), Targets(genres=("ambient",))) is None


def test_feature_fit_weights_the_features_it_compares():
    fit = feature_fit(_music("a", genre="ambient", energy=0.6), Targets(genres=("ambient",), energy=0.2))

    # genre 1.0 at weight 3, energy closeness 0.6 at weight 2.
    assert fit.value == pytest.approx((3 * 1.0 + 2 * 0.6) / 5)


def test_tempo_is_compared_on_a_scaled_distance():
    fit = feature_fit(_music("a", tempo_bpm=150.0), Targets(tempo_bpm=120.0))

    # 30 BPM apart is 0.3 on the 100 BPM scale.
    assert fit.value == pytest.approx(0.7)


def test_missing_features_are_left_out_and_never_filled_in():
    signals = SessionSignals(context=ListeningContext(temporary_genres=("ambient",), target_energy=0.2))
    genre_only = _candidate("genre-only", genre="ambient")
    complete = _candidate("complete", genre="ambient", energy=0.6)

    decision = decide([complete, genre_only], signals, rng=_never_explore())

    assert _ids(decision) == ["genre-only", "complete"]
    assert _pick(decision, "genre-only").score.intent.value == 1.0
    assert [feature.feature for feature in _pick(decision, "genre-only").score.intent.features] == ["genre"]


def test_a_candidate_with_nothing_to_compare_never_outranks_a_scorable_one():
    """A track with no score (spec §13) only fills a queue the scorable tracks cannot fill."""
    mismatch = _candidate("mismatch", genre="rock")
    unknown = _candidate("unknown")

    decision = decide([unknown, mismatch], SessionSignals(context=_AMBIENT), rng=_never_explore())

    assert _ids(decision) == ["mismatch", "unknown"]
    assert _pick(decision, "mismatch").score.combined == pytest.approx(_combined(0.0))
    assert _pick(decision, "unknown").score.combined > _pick(decision, "mismatch").score.combined
    assert not _pick(decision, "unknown").score.is_scorable
    # Surfaced without a score: the neutral session fit is not a score for the track.
    assert [recommendation.score_breakdown.normalized_score for recommendation in decision.recommendations()] == [
        pytest.approx(_combined(0.0)), None
    ]


# --- Similarity and session fit -------------------------------------------------------------


def test_candidate_similarity_uses_only_common_features():
    similarity = candidate_similarity(_music("a", genre="rock", energy=0.5), _music("b", genre="rock", mood="happy"))

    assert (similarity.value, similarity.feature_count) == (1.0, 1)


def test_candidate_similarity_weights_common_features():
    similarity = candidate_similarity(_music("a", genre="rock", mood="calm", energy=0.5), _music("b", genre="rock", mood="happy", energy=0.4))

    assert similarity.value == pytest.approx((3 * 1.0 + 3 * 0.0 + 2 * 0.9) / 8)
    assert similarity.feature_count == 3


def test_candidate_similarity_is_unavailable_without_common_features():
    assert candidate_similarity(_music("a", genre="rock"), _music("b", energy=0.4)) is None


def test_no_evidence_gives_a_neutral_session_fit():
    fit = session_fit(_music("a", genre="rock"), ())

    assert (fit.value, fit.has_evidence) == (0.5, False)


def test_evidence_that_cannot_be_compared_is_not_evidence():
    fit = session_fit(_music("a", genre="rock"), (SessionEvidence(_music("x", energy=0.3), 1.0),))

    assert (fit.value, fit.has_evidence) == (0.5, False)


def test_session_fit_follows_the_spec_formula_with_recency():
    """net = sum(e*s*r) / sum(|e|*r), r = 0.85 ** age with the latest at age 0; fit = (net + 1) / 2."""
    rejected_now = SessionEvidence(_music("rejected", genre="rock"), -1.0)
    liked_before = SessionEvidence(_music("liked", genre="rock"), 1.0)

    fit = session_fit(_music("a", genre="rock"), (rejected_now, liked_before))

    net = (-1.0 * 1.0 * 1.0 + 1.0 * 1.0 * 0.85) / (1.0 + 0.85)
    assert fit.value == pytest.approx((net + 1) / 2)
    assert fit.has_evidence


# --- Combining the stages ---------------------------------------------------------------------


def test_stage_weights_are_renormalized_over_the_available_stages():
    candidate = _candidate("a", genre="ambient", energy=0.2)
    profile = UserProfile(preferred_genres=("ambient",))

    without_history = score(candidate, SessionSignals(context=_AMBIENT))
    with_history = score(candidate, SessionSignals(context=_AMBIENT, long_term=profile))
    nothing_to_compare = score(candidate, SessionSignals())

    assert [(name, pytest.approx(weight)) for name, weight, _ in without_history.stage_weights] == [
        ("intent", pytest.approx(_INTENT_SHARE)), ("session", pytest.approx(_SESSION_SHARE))
    ]
    assert [(name, weight) for name, weight, _ in with_history.stage_weights] == [
        ("intent", pytest.approx(0.55)), ("session", pytest.approx(0.30)), ("long_term", pytest.approx(0.15))
    ]
    assert [(name, weight) for name, weight, _ in nothing_to_compare.stage_weights] == [("session", 1.0)]
    assert (nothing_to_compare.combined, nothing_to_compare.is_scorable) == (0.5, False)


# --- Acceptance: no feedback ---------------------------------------------------------------------


def test_without_feedback_the_queue_follows_intent():
    candidates = [_candidate(track_id, genre=genre) for track_id, genre in (("r1", "rock"), ("a1", "ambient"), ("a2", "ambient"), ("r2", "rock"), ("a3", "ambient"))]

    decision = decide(candidates, SessionSignals(context=_AMBIENT), rng=_never_explore())

    assert _ids(decision) == ["a1", "a2", "a3"]
    assert [pick.rank for pick in decision.picks] == [1, 2, 3]
    assert all(pick.score.combined == pytest.approx(_combined(1.0)) for pick in decision.picks)
    assert all(not pick.score.session.has_evidence for pick in decision.picks)
    assert (decision.policy_version, decision.exploration_rate, decision.explored, decision.second_plays_first) == ("policy-v1", 0.10, False, False)


def test_a_genre_only_library_is_not_treated_as_duplicates():
    candidates = [_candidate(f"a{index}", genre="ambient") for index in range(4)]

    decision = decide(candidates, SessionSignals(context=_AMBIENT), rng=_never_explore())

    assert all(pick.penalties == () for pick in decision.picks)


# --- Acceptance: positive feedback ---------------------------------------------------------------


def test_positive_feedback_pulls_similar_tracks_up():
    candidates = [_candidate("a1", genre="ambient", mood="dark"), _candidate("a2", genre="ambient", mood="calm")]
    liked = SessionEvidence(_music("liked", genre="ambient", mood="calm"), POLICY_V1.more_like_this_weight)

    before = decide(candidates, SessionSignals(context=_AMBIENT), rng=_never_explore())
    after = decide(candidates, SessionSignals(context=_AMBIENT, evidence=(liked,)), rng=_never_explore())

    assert _ids(before) == ["a1", "a2"]
    assert _ids(after) == ["a2", "a1"]
    assert _pick(after, "a2").score.session.value == 1.0
    assert _pick(after, "a1").score.session.value == pytest.approx(0.75)


# --- Acceptance: early skip and Not for me ---------------------------------------------------------


def test_an_early_skip_counts_against_similar_tracks_less_than_not_for_me():
    """Feedback Policy v1 weighs an early skip at -0.5 and Not for me at -1.0 (spec §17)."""
    candidate = _music("a", genre="ambient", mood="dark")
    liked_before = SessionEvidence(_music("liked", genre="ambient", mood="calm"), 1.0)
    skipped = SessionEvidence(_music("skipped", genre="ambient", mood="dark"), -0.5)
    rejected = SessionEvidence(_music("rejected", genre="ambient", mood="dark"), -1.0)

    after_skip = session_fit(candidate, (skipped, liked_before))
    after_rejection = session_fit(candidate, (rejected, liked_before))

    assert after_rejection.value < after_skip.value < 0.5
    assert after_skip.value == pytest.approx(((-0.5 + 1.0 * 0.5 * 0.85) / (0.5 + 0.85) + 1) / 2)


def test_an_early_skip_lowers_similar_tracks_without_excluding_the_skipped_one():
    skipped = _candidate("skipped", genre="ambient", mood="dark")
    similar = _candidate("similar", genre="ambient", mood="dark")
    different = _candidate("different", genre="ambient", mood="calm")
    signals = SessionSignals(context=_AMBIENT, evidence=(SessionEvidence(skipped.music, -0.5),))

    decision = decide([similar, skipped, different], signals, rng=_never_explore())

    assert _ids(decision) == ["different", "similar", "skipped"]


def test_not_for_me_excludes_the_track_and_pushes_similar_tracks_down():
    rejected = _candidate("x", genre="ambient")
    candidates = [rejected, _candidate("y", genre="ambient"), _candidate("z", genre="rock"), _candidate("w", genre="rock")]
    signals = SessionSignals(evidence=(SessionEvidence(rejected.music, POLICY_V1.not_for_me_weight),), excluded_track_ids=frozenset({"x"}))

    decision = decide(candidates, signals, rng=_never_explore())

    assert _ids(decision) == ["w", "z", "y"]
    assert _pick(decision, "y").score.session.value == 0.0
    assert _pick(decision, "w").score.session.value == 0.5


# --- Acceptance: current intent against history ----------------------------------------------------------


def test_current_intent_wins_over_long_term_history():
    history = UserProfile(preferred_genres=("rock",), preferred_energy=0.9)
    signals = SessionSignals(context=ListeningContext(temporary_genres=("ambient",), target_energy=0.2), long_term=history)
    calm = _candidate("calm", genre="ambient", energy=0.2)
    loud = _candidate("loud", genre="rock", energy=0.9)

    decision = decide([loud, calm], signals, rng=_never_explore())

    assert _ids(decision) == ["calm", "loud"]
    # B10: a profile that does not match is neutral (0.5) in the long-term stage, not 0: history is positive affinity.
    assert _pick(decision, "calm").score.combined == pytest.approx(0.55 * 1.0 + 0.30 * 0.5 + 0.15 * 0.5)
    assert _pick(decision, "loud").score.combined == pytest.approx(0.55 * 0.0 + 0.30 * 0.5 + 0.15 * 1.0)


def test_history_never_fills_the_intent_stage_and_counts_only_in_its_own():
    """B10: what the listener left open stays open in intent fit; the profile is the .15 long-term stage alone.

    (B5 filled open intent targets from history, which would have counted a profile twice. Nothing supplied a
    profile before B10, so no earlier output changes.)
    """
    history = UserProfile(preferred_genres=("rock",), preferred_moods=("happy",), preferred_energy=0.9, preferred_danceability=0.7)
    context = ListeningContext(temporary_genres=("ambient",), desired_mood="calm", target_energy=0.2)

    targets = Targets.from_context(context)

    assert (targets.genres, targets.moods, targets.energy, targets.danceability) == (("ambient",), ("calm",), 0.2, None)
    assert Targets.from_context(ListeningContext(temporary_moods=("dark",), desired_mood="calm")).moods == ("dark",)
    assert Targets.from_context(ListeningContext()) == Targets()
    open_intent = score(_candidate("r", genre="rock", mood="happy"), SessionSignals(long_term=history))
    assert open_intent.intent is None  # nothing asked for: no intent stage
    assert [(name, pytest.approx(weight)) for name, weight, _ in open_intent.stage_weights] == [
        ("session", pytest.approx(0.30 / 0.45)), ("long_term", pytest.approx(0.15 / 0.45))
    ]


# --- B10: the long-term stage with a stored profile --------------------------------------------------------


def test_missing_long_term_features_are_omitted_and_the_stage_renormalized():
    """A profile feature a candidate lacks is left out; with nothing left to compare, the whole stage is (D21, spec §14)."""
    genre_only = _candidate("a", genre="afrobeats")

    energy_profile = score(genre_only, SessionSignals(long_term=UserProfile(preferred_energy=0.6)))
    mixed_profile = score(genre_only, SessionSignals(long_term=UserProfile(preferred_genres=("afrobeats",), preferred_energy=0.6)))

    assert energy_profile.long_term is None and [name for name, _, _ in energy_profile.stage_weights] == ["session"]
    assert [feature.feature for feature in mixed_profile.long_term.features] == ["genre"]  # energy omitted, genre kept
    assert mixed_profile.long_term.value == 1.0
    assert [(name, pytest.approx(weight)) for name, weight, _ in mixed_profile.stage_weights] == [
        ("session", pytest.approx(0.30 / 0.45)), ("long_term", pytest.approx(0.15 / 0.45))
    ]


_HISTORY_A = UserProfile(preferred_genres=("afrobeats",))  # a stored long-term preference for genre A


def test_a_long_term_preference_is_positive_affinity_never_a_penalty():
    """B10: no match with the profile is neutral (0.5), a full match 1.0, in between in proportion (TD-021)."""
    signals = SessionSignals(long_term=UserProfile(preferred_genres=("afrobeats",), preferred_energy=0.6))

    mismatch = score(_candidate("j", genre="jazz", energy=0.1), signals)  # genre 0, energy 0.5 apart: raw 0
    full = score(_candidate("a", genre="afrobeats", energy=0.6), signals)
    partial = score(_candidate("p", genre="jazz", energy=0.6), signals)  # energy matches, genre does not

    assert (mismatch.long_term.value, mismatch.stage_weights[-1]) == (0.0, ("long_term", pytest.approx(1 / 3), 0.5))
    assert full.stage_weights[-1][2] == 1.0
    assert partial.stage_weights[-1][2] == pytest.approx(0.5 + 0.5 * partial.long_term.value)
    assert 0.5 < partial.stage_weights[-1][2] < 1.0


def test_with_no_intent_strong_session_evidence_for_b_beats_a_long_term_preference_for_a():
    signals = SessionSignals(long_term=_HISTORY_A, evidence=(SessionEvidence(_music("liked", genre="jazz"), 1.0),))

    jazz, afrobeats = score(_candidate("j", genre="jazz"), signals), score(_candidate("a", genre="afrobeats"), signals)

    assert jazz.combined == pytest.approx((0.30 * 1.0 + 0.15 * 0.5) / 0.45)  # 0.833
    assert afrobeats.combined == pytest.approx((0.30 * 0.5 + 0.15 * 1.0) / 0.45)  # 0.667
    assert _ids(decide([_candidate("a", genre="afrobeats"), _candidate("j", genre="jazz")], signals, rng=_never_explore()))[0] == "j"


def test_a_long_term_preference_still_lifts_its_genre_when_the_session_says_nothing():
    signals = SessionSignals(long_term=_HISTORY_A)

    assert score(_candidate("a", genre="afrobeats"), signals).combined == pytest.approx((0.30 * 0.5 + 0.15 * 1.0) / 0.45)
    assert score(_candidate("j", genre="jazz"), signals).combined == pytest.approx(0.5)  # neutral on both stages
    assert _ids(decide([_candidate("j", genre="jazz"), _candidate("a", genre="afrobeats")], signals, rng=_never_explore()))[0] == "a"


def test_explicit_intent_outranks_both_session_evidence_and_long_term_history():
    """Session evidence and history both favour A; the listener asks for B. Intent fit is not softened: A scores 0."""
    signals = SessionSignals(
        context=ListeningContext(temporary_genres=("jazz",)), long_term=_HISTORY_A,
        evidence=(SessionEvidence(_music("liked", genre="afrobeats"), 1.0),),
    )

    jazz, afrobeats = score(_candidate("j", genre="jazz"), signals), score(_candidate("a", genre="afrobeats"), signals)

    assert afrobeats.intent.value == 0.0  # an explicit request may rightly give a mismatch nothing
    assert jazz.combined == pytest.approx(0.55 * 1.0 + 0.30 * 0.5 + 0.15 * 0.5)  # 0.775
    assert afrobeats.combined == pytest.approx(0.55 * 0.0 + 0.30 * 1.0 + 0.15 * 1.0)  # 0.45
    assert jazz.combined > afrobeats.combined


def test_negative_session_evidence_overcomes_a_conflicting_long_term_preference():
    """Session fit stays signed: a refusal of an A track this session outweighs the stored preference for A."""
    signals = SessionSignals(long_term=_HISTORY_A, evidence=(SessionEvidence(_music("refused", genre="afrobeats"), -1.0),))

    afrobeats, jazz = score(_candidate("a", genre="afrobeats"), signals), score(_candidate("j", genre="jazz"), signals)

    assert afrobeats.session.value == 0.0  # still negative evidence, not lifted to neutral
    assert afrobeats.combined == pytest.approx((0.30 * 0.0 + 0.15 * 1.0) / 0.45)  # 0.333
    assert jazz.combined == pytest.approx((0.30 * 0.5 + 0.15 * 0.5) / 0.45)  # 0.5
    assert jazz.combined > afrobeats.combined


def test_without_a_long_term_profile_scores_are_exactly_as_before_b10():
    """No profile, or an empty one, leaves no long-term stage: the pre-B10 renormalized intent and session scores."""
    context = ListeningContext(temporary_genres=("ambient",), target_energy=0.2)
    evidence = (SessionEvidence(_music("liked", genre="ambient", energy=0.3), 1.0),)
    candidate = _candidate("a", genre="ambient", energy=0.25)

    without, empty = score(candidate, SessionSignals(context=context, evidence=evidence)), score(
        candidate, SessionSignals(context=context, evidence=evidence, long_term=UserProfile())
    )

    assert without == empty
    assert without.long_term is None and [name for name, _, _ in without.stage_weights] == ["intent", "session"]
    assert without.combined == pytest.approx((0.55 * without.intent.value + 0.30 * without.session.value) / 0.85)


# --- Acceptance: a finite library ----------------------------------------------------------------------


@pytest.mark.parametrize("pool_size, window", [(1, 1), (2, 1), (4, 1), (10, 7), (23, 20), (500, 20)])
def test_the_cooldown_shrinks_for_small_libraries(pool_size, window):
    assert cooldown_window(pool_size) == window


def test_a_small_library_repeats_tracks_after_the_cooldown_least_recent_first():
    candidates = [_candidate(f"t{index}", genre="ambient") for index in range(1, 5)]
    signals = SessionSignals(context=_AMBIENT, recent_track_ids=("t4", "t3", "t2", "t1"), last_played=candidates[3])

    decision = decide(candidates, signals, rng=_never_explore())

    assert _ids(decision) == ["t1", "t2", "t3"]
    assert all(pick.penalties == ("recently played",) for pick in decision.picks)
    # Played 3, 2, and 1 plays ago: the penalty fades by a twentieth per play.
    assert [pick.ranking_score for pick in decision.picks] == pytest.approx([_combined(1.0) - 0.10 * (1 - age / 20) for age in (3, 2, 1)])


def test_a_small_library_rotates_instead_of_alternating_two_tracks():
    candidates = [_candidate(f"t{index}", genre="ambient") for index in range(1, 5)]
    signals = SessionSignals(context=_AMBIENT, recent_track_ids=("t2", "t1"), last_played=candidates[1])

    decision = decide(candidates, signals, rng=_never_explore())

    assert _ids(decision) == ["t3", "t4", "t1"]


def test_in_a_small_library_intent_still_wins_over_rotation():
    candidates = [_candidate("a1", genre="ambient"), _candidate("a2", genre="ambient"), _candidate("r1", genre="rock"), _candidate("r2", genre="rock")]
    signals = SessionSignals(context=_AMBIENT, recent_track_ids=("a2", "a1"), last_played=candidates[1])

    decision = decide(candidates, signals, rng=_never_explore())

    assert _ids(decision)[0] == "a1"


def test_exploration_never_picks_a_recently_played_track():
    library = _exploration_library()
    signals = SessionSignals(context=_MID_ENERGY, recent_track_ids=("e1",))

    decision = decide(library, signals, rng=_always_explore())

    assert "e1" not in _ids(decision)
    assert not decision.explored


def test_a_large_library_holds_back_the_last_twenty_plays():
    candidates = [_candidate(f"t{index:02d}", genre="ambient") for index in range(25)]
    recent = tuple(f"t{index:02d}" for index in range(21))

    decision = decide(candidates, SessionSignals(context=_AMBIENT, recent_track_ids=recent), rng=_never_explore())

    assert _ids(decision) == ["t20", "t21", "t22"]


def test_a_rejected_track_does_not_use_up_the_cooldown():
    """Five tracks remain after a rejection, so the two most recent plays of those five cool down."""
    candidates = [_candidate("rejected", genre="ambient"), _candidate("a", genre="ambient"), _candidate("b", genre="ambient")]
    candidates += [_candidate(track_id, genre="rock") for track_id in ("c", "d", "e")]
    signals = SessionSignals(context=_AMBIENT, recent_track_ids=("rejected", "a", "b"), excluded_track_ids=frozenset({"rejected"}))

    decision = decide(candidates, signals, rng=_never_explore())

    assert _ids(decision) == ["c", "d", "e"]


def test_a_one_track_library_has_nothing_to_queue_while_it_plays():
    only = _candidate("only", genre="ambient")

    decision = decide([only], SessionSignals(context=_AMBIENT, recent_track_ids=("only",), last_played=only), rng=_always_explore())

    assert (decision.picks, decision.recommendations(), decision.explored) == ((), [], False)


def test_unavailable_and_rejected_tracks_are_never_queued():
    candidates = [_candidate("missing", genre="ambient", available=False), _candidate("rejected", genre="ambient"), _candidate("ok", genre="rock")]

    decision = decide(candidates, SessionSignals(context=_AMBIENT, excluded_track_ids=frozenset({"rejected"})), rng=_never_explore())

    assert _ids(decision) == ["ok"]


# --- Diversity ---------------------------------------------------------------------------------------


def test_a_repeated_artist_is_held_back_a_place():
    candidates = [_candidate("a1", artist="X", energy=0.5), _candidate("a2", artist="x", energy=0.5), _candidate("b", artist="Y", energy=0.45)]

    decision = decide(candidates, SessionSignals(context=_MID_ENERGY), rng=_never_explore())

    assert _ids(decision) == ["a1", "b", "a2"]
    assert _pick(decision, "a2").penalties == ("repeated artist",)
    assert _pick(decision, "a2").ranking_score == pytest.approx(_combined(1.0) - 0.10)


def test_the_artist_that_just_played_counts_as_a_repeat():
    last = _candidate("last", artist="X", energy=0.9)
    candidates = [_candidate("a", artist="X", energy=0.5), _candidate("b", artist="Y", energy=0.45)]

    decision = decide(candidates, SessionSignals(context=_MID_ENERGY, last_played=last), rng=_never_explore())

    assert _ids(decision)[0] == "b"
    assert _pick(decision, "a").penalties == ("repeated artist",)


def test_unknown_artists_are_never_repeats():
    candidates = [_candidate("a", energy=0.5), _candidate("b", energy=0.5)]

    decision = decide(candidates, SessionSignals(context=_MID_ENERGY), rng=_never_explore())

    assert all(pick.penalties == () for pick in decision.picks)


def test_a_near_duplicate_is_held_back_a_place():
    candidates = [
        _candidate("d1", genre="ambient", mood="calm", energy=0.3),
        _candidate("d2", genre="ambient", mood="calm", energy=0.3),
        _candidate("o", genre="ambient", mood="dark", energy=0.3),
    ]

    decision = decide(candidates, SessionSignals(context=_AMBIENT), rng=_never_explore())

    assert _ids(decision) == ["d1", "o", "d2"]
    assert _pick(decision, "d2").penalties == ("near-duplicate",)


def test_diversity_never_overrides_explicit_intent():
    candidates = [_candidate("a1", artist="X", genre="ambient"), _candidate("a2", artist="X", genre="ambient"), _candidate("r", artist="Y", genre="rock")]

    decision = decide(candidates, SessionSignals(context=_AMBIENT), rng=_never_explore())

    assert _ids(decision) == ["a1", "a2", "r"]


# --- Acceptance: exploration -----------------------------------------------------------------------------


def _exploration_outcome(weight):
    return SessionEvidence(_music("explored", genre="jazz"), weight, is_exploration=True)


def test_automatic_exploration_runs_at_about_ten_percent():
    assert exploration_rate(SessionSignals()) == 0.10


def test_listener_controls_do_not_move_the_automatic_rate():
    for control in (TurnKind.SURPRISE_ME, TurnKind.TRY_SOMETHING_DIFFERENT, TurnKind.MORE_FAMILIAR):
        assert exploration_rate(SessionSignals(pending_control=control)) == 0.10


def test_a_failed_exploration_lowers_the_rate_and_a_successful_one_raises_it():
    assert exploration_rate(SessionSignals(evidence=(_exploration_outcome(-1.0),))) == pytest.approx(0.05)
    assert exploration_rate(SessionSignals(evidence=(_exploration_outcome(1.0),))) == pytest.approx(0.125)


def test_only_recent_exploration_outcomes_count_and_one_skip_never_stops_exploration():
    four_failures = tuple(_exploration_outcome(-0.5) for _ in range(4))

    assert exploration_rate(SessionSignals(evidence=(_exploration_outcome(-0.5),))) > 0
    assert exploration_rate(SessionSignals(evidence=four_failures)) == pytest.approx(0.10 * 0.5 ** 3)


def test_evidence_about_ordinary_picks_does_not_move_exploration():
    ordinary = SessionEvidence(_music("ordinary", genre="jazz"), -1.0)

    assert exploration_rate(SessionSignals(evidence=(ordinary,))) == 0.10


def test_the_exploration_rate_is_capped():
    successes = tuple(_exploration_outcome(1.0) for _ in range(3))

    assert exploration_rate(SessionSignals(evidence=successes), RecommendationPolicy(exploration_rate=0.40)) == 0.50


def _exploration_library():
    return [
        _candidate("p1", artist="A", energy=0.50),
        _candidate("p2", artist="B", energy=0.48),
        _candidate("p3", artist="C", energy=0.46),
        _candidate("p4", artist="D", energy=0.44),  # plausible but too close to p1 to be novel
        _candidate("e1", artist="E", energy=0.75),  # plausible and novel
        _candidate("far", artist="F", energy=1.00),  # novel but below the plausibility floor
    ]


def test_exploration_gives_the_last_slot_to_the_best_plausible_novel_track():
    decision = decide(_exploration_library(), SessionSignals(context=_MID_ENERGY), rng=_always_explore())

    assert _ids(decision) == ["p1", "p2", "e1"]
    assert (decision.explored, decision.exploration_track_ids, decision.steering) == (True, frozenset({"e1"}), None)
    assert (_pick(decision, "e1").is_exploration, _pick(decision, "e1").rank) == (True, 5)
    assert _pick(decision, "e1").score.combined == pytest.approx(_combined(0.75))


def test_without_a_plausible_novel_track_there_is_no_exploration():
    library = [candidate for candidate in _exploration_library() if candidate.track_id != "e1"]

    decision = decide(library, SessionSignals(context=_MID_ENERGY), rng=_always_explore())

    assert _ids(decision) == ["p1", "p2", "p3"]
    assert (decision.explored, decision.exploration_track_ids) == (False, frozenset())


def test_a_track_with_no_score_is_never_an_automatic_exploration_pick():
    """Nothing about it can be compared, so it has no score, and automatic exploration needs one."""
    library = [candidate for candidate in _exploration_library() if candidate.track_id != "e1"] + [_candidate("blank")]

    decision = decide(library, SessionSignals(context=_MID_ENERGY), rng=_always_explore())

    assert _ids(decision) == ["p1", "p2", "p3"]
    assert not decision.explored


def test_whether_automatic_exploration_happens_depends_on_the_rate():
    library = _exploration_library()

    assert not decide(library, SessionSignals(context=_MID_ENERGY), rng=_FixedRandom(0.2)).explored
    assert decide(library, SessionSignals(context=_MID_ENERGY), rng=_FixedRandom(0.05)).explored


def test_a_seeded_rng_makes_decisions_reproducible():
    library = _exploration_library()
    eager = RecommendationPolicy(exploration_rate=0.5)

    runs = [_ids(decide(library, SessionSignals(context=_MID_ENERGY), eager, random.Random(seed))) for seed in (11, 11, 12, 12)]

    assert runs[0] == runs[1] and runs[2] == runs[3]


# --- Listener controls: one-refresh directives that are part of current intent -------------------------------

_AMBIENT_MID = ListeningContext(temporary_genres=("ambient",), target_energy=0.5)


class _NoDraw(random.Random):
    """A control decides deterministically, so drawing from this generator fails the test."""

    def random(self):
        raise AssertionError("a listener control must not depend on the random draw")


def _genre_library(in_genre_novelty=True):
    library = [
        _candidate("a1", artist="A", genre="ambient", energy=0.5),
        _candidate("a2", artist="B", genre="ambient", energy=0.5),
        _candidate("a3", artist="C", genre="ambient", energy=0.5),
        _candidate("r", artist="R", genre="rock", energy=0.5),  # outside the genre; plausible on energy alone
    ]
    if in_genre_novelty:
        library.append(_candidate("a4", artist="D", genre="ambient", energy=1.0))  # in the genre, plausible, novel
    return library


def _genre_only_library(*extra):
    return [_candidate(f"a{index}", artist=f"A{index}", genre="ambient") for index in range(1, 5)] + list(extra)


def _automatic(library, **signals):
    """Automatic exploration, with a draw that always explores."""
    context = signals.pop("context", _AMBIENT_MID)
    return decide(library, SessionSignals(context=context, **signals), rng=_always_explore())


def _directed(library, control, **signals):
    context = signals.pop("context", _AMBIENT_MID)
    return decide(library, SessionSignals(context=context, pending_control=control, **signals), rng=_NoDraw(0))


def test_without_a_control_exploration_stays_in_the_requested_genre():
    library = _genre_library(in_genre_novelty=False)
    out_of_genre = library[3]

    decision = _automatic(library)

    assert score(out_of_genre, SessionSignals(context=_AMBIENT_MID)).combined >= POLICY_V1.exploration_floor
    assert (_ids(decision), decision.explored) == (["a1", "a2", "a3"], False)


def test_without_a_control_exploration_finds_novelty_within_the_genre():
    decision = _automatic(_genre_library())

    assert _ids(decision) == ["a1", "a2", "a4"]
    assert not _pick(decision, "a4").genre_set_aside


def test_surprise_me_deterministically_takes_the_last_slot_within_the_requested_genre():
    """Outside the genre, r would score higher on energy alone, but the genre holds while it offers novelty."""
    decision = _directed(_genre_library(), TurnKind.SURPRISE_ME)

    assert _ids(decision) == ["a1", "a2", "a4"]
    assert (_pick(decision, "a4").is_exploration, _pick(decision, "a4").genre_set_aside) == (True, False)
    assert (decision.steering, decision.explored) == (TurnKind.SURPRISE_ME, True)


def test_surprise_me_sets_the_genre_aside_only_when_nothing_in_it_is_novel():
    decision = _directed(_genre_library(in_genre_novelty=False), TurnKind.SURPRISE_ME)

    explored = _pick(decision, "r")
    assert _ids(decision) == ["a1", "a2", "r"]
    assert (explored.is_exploration, explored.genre_set_aside) == (True, True)
    # Judged on the intent without the genre: energy alone, a perfect fit.
    assert [feature.feature for feature in explored.score.intent.features] == ["energy"]
    assert explored.score.combined == pytest.approx(_combined(1.0))


def test_try_something_different_makes_a_track_outside_the_genre_the_next_to_play():
    """Even with novelty inside the genre, it steps outside at once; the in-intent picks follow."""
    decision = _directed(_genre_library(), TurnKind.TRY_SOMETHING_DIFFERENT)

    assert _ids(decision) == ["r", "a1", "a2"]
    assert (decision.picks[0].is_exploration, decision.picks[0].genre_set_aside) == (True, True)
    assert [recommendation.rank for recommendation in decision.recommendations()] == [5, 1, 2]
    assert (decision.steering, decision.second_plays_first) == (TurnKind.TRY_SOMETHING_DIFFERENT, False)


def test_more_familiar_suppresses_exploration_for_the_refresh():
    """The automatic draw would explore here; More familiar overrides it, without drawing."""
    signals = SessionSignals(context=_AMBIENT_MID, pending_control=TurnKind.MORE_FAMILIAR)

    decision = decide(_genre_library(), signals, rng=_NoDraw(0))

    assert _automatic(_genre_library()).explored
    assert (_ids(decision), decision.explored, decision.steering) == (["a1", "a2", "a3"], False, TurnKind.MORE_FAMILIAR)


def test_a_control_with_no_qualifying_track_changes_nothing():
    """In a library of one genre nothing is novel, inside the genre or out."""
    for control in (TurnKind.SURPRISE_ME, TurnKind.TRY_SOMETHING_DIFFERENT):
        decision = _directed(_genre_only_library(), control, context=_AMBIENT)
        assert (_ids(decision), decision.explored) == (["a1", "a2", "a3"], False)


@pytest.mark.parametrize(
    "control, order", [(TurnKind.SURPRISE_ME, ["a1", "a2", "r1"]), (TurnKind.TRY_SOMETHING_DIFFERENT, ["r1", "a1", "a2"])]
)
def test_in_a_genre_only_library_a_control_uses_the_fallback_rule(control, order):
    """Tags give genre alone. With the genre set aside, nothing about r1 can be compared, so it gets no
    score: none is invented. It qualifies by the explicit rule (a known genre, playable, not rejected)
    and is surfaced without a score."""
    library = _genre_only_library(_candidate("r1", artist="R", genre="rock"))

    decision = _directed(library, control, context=_AMBIENT)

    explored = _pick(decision, "r1")
    assert _ids(decision) == order
    assert (explored.is_exploration, explored.genre_set_aside, explored.score.is_scorable) == (True, True, False)
    assert (explored.score.intent, explored.score.session.has_evidence) == (None, False)
    recommendation = decision.recommendations()[order.index("r1")]
    assert (recommendation.score_breakdown.normalized_score, recommendation.score_breakdown.components) == (None, ())
    assert not _automatic(library, context=_AMBIENT).explored


def test_a_track_scored_outside_the_genre_comes_before_one_admitted_by_the_rule():
    """j has nothing to compare once the genre is set aside; r has energy, a perfect fit."""
    library = _genre_library(in_genre_novelty=False) + [_candidate("j", artist="J", genre="jazz")]

    with_both = _directed(library, TurnKind.TRY_SOMETHING_DIFFERENT)
    rule_only = _directed([candidate for candidate in library if candidate.track_id != "r"], TurnKind.TRY_SOMETHING_DIFFERENT)

    assert _ids(with_both) == ["r", "a1", "a2"]
    assert with_both.picks[0].score.is_scorable
    assert _ids(rule_only) == ["j", "a1", "a2"]
    assert not rule_only.picks[0].score.is_scorable


def test_setting_the_genre_aside_still_respects_session_evidence():
    """A rejected genre stays out: its tracks lose session fit and fall below the plausibility floor.
    Evidence exists, so the fallback rule does not apply to them."""
    rejected = _candidate("r0", artist="R", genre="rock")
    library = _genre_only_library(rejected, _candidate("r1", artist="S", genre="rock"), _candidate("j1", artist="J", genre="jazz"))
    signals = dict(context=_AMBIENT, evidence=(SessionEvidence(rejected.music, -1.0),), excluded_track_ids=frozenset({"r0"}))

    decision = _directed(library, TurnKind.TRY_SOMETHING_DIFFERENT, **signals)
    only_the_rejected_genre = _directed(library[:-1], TurnKind.TRY_SOMETHING_DIFFERENT, **signals)

    assert _ids(decision) == ["j1", "a1", "a2"]
    assert (_ids(only_the_rejected_genre), only_the_rejected_genre.explored) == (["a1", "a2", "a3"], False)


def test_the_fallback_rule_never_admits_an_unknown_or_rejected_track():
    unknown = _directed(_genre_only_library(_candidate("blank")), TurnKind.TRY_SOMETHING_DIFFERENT, context=_AMBIENT)
    rejected = _directed(
        _genre_only_library(_candidate("r1", artist="R", genre="rock")), TurnKind.TRY_SOMETHING_DIFFERENT,
        context=_AMBIENT, excluded_track_ids=frozenset({"r1"}),
    )

    assert (unknown.explored, rejected.explored) == (False, False)


def test_a_different_track_playing_first_is_never_swapped_behind_the_next():
    """a1 is close enough and more novel than j relative to what just played, so an ordinary #1 would
    yield to it; the track Try something different chose stays first."""
    last = _candidate("r0", artist="L", genre="rock", energy=0.9)
    library = [_candidate(f"a{index}", artist=f"A{index}", genre="ambient", energy=0.1) for index in range(1, 4)]
    library.append(_candidate("j", artist="J", genre="jazz", energy=0.5))
    context = ListeningContext(temporary_genres=("ambient",), target_energy=0.1)

    decision = _directed(library, TurnKind.TRY_SOMETHING_DIFFERENT, context=context, last_played=last)

    assert decision.picks[0].ranking_score - decision.picks[1].ranking_score <= POLICY_V1.swap_margin
    assert (_ids(decision), decision.second_plays_first) == (["j", "a1", "a2"], False)


# --- Acceptance: the #2 safety threshold ------------------------------------------------------------------


def _novelty_library(second_energy):
    return [
        _candidate("c1", artist="Y", energy=0.50),
        _candidate("c2", artist="Z", energy=second_energy),
        _candidate("c3", artist="W", energy=0.30),
    ]


def test_a_close_and_more_novel_second_plays_first():
    last = _candidate("last", artist="X", energy=0.50)

    decision = decide(_novelty_library(0.45), SessionSignals(context=_MID_ENERGY, last_played=last), rng=_never_explore())

    assert _ids(decision) == ["c2", "c1", "c3"]
    assert decision.second_plays_first
    assert [recommendation.rank for recommendation in decision.recommendations()] == [2, 1, 3]


def test_a_second_more_than_the_margin_behind_does_not_play_first():
    last = _candidate("last", artist="X", energy=0.50)

    decision = decide(_novelty_library(0.35), SessionSignals(context=_MID_ENERGY, last_played=last), rng=_never_explore())

    assert _combined(1.0) - _combined(0.85) > 0.08
    assert (_ids(decision), decision.second_plays_first) == (["c1", "c2", "c3"], False)


def test_a_second_that_is_not_more_novel_does_not_play_first():
    last = _candidate("last", artist="X", energy=0.45)

    decision = decide(_novelty_library(0.45), SessionSignals(context=_MID_ENERGY, last_played=last), rng=_never_explore())

    assert (_ids(decision), decision.second_plays_first) == (["c1", "c2", "c3"], False)


def test_a_second_by_the_artist_that_just_played_does_not_play_first():
    """Its features are further from the last play, but the same artist is not novelty. No penalty, to isolate the rule."""
    last = _candidate("last", artist="Z", energy=0.90)
    policy = RecommendationPolicy(artist_repeat_penalty=0.0)

    decision = decide(_novelty_library(0.45), SessionSignals(context=_MID_ENERGY, last_played=last), policy, _never_explore())

    assert (_ids(decision), decision.second_plays_first) == (["c1", "c2", "c3"], False)


def test_an_unscored_second_never_plays_ahead_of_a_scored_first():
    """#1 is by the artist that just played, which makes any #2 more novel, and the unscored #2 is
    within the margin of #1's penalized score; a track with no score still never goes first."""
    last = _candidate("last", artist="X", genre="ambient", energy=0.5)
    scored_first = _candidate("a1", artist="X", genre="ambient", energy=1.0)
    unscored = _candidate("u", artist="U")

    decision = decide([unscored, scored_first], SessionSignals(context=_AMBIENT_MID, last_played=last), rng=_never_explore())

    assert decision.picks[0].ranking_score - decision.picks[1].ranking_score <= POLICY_V1.swap_margin
    assert (_ids(decision), decision.second_plays_first) == (["a1", "u"], False)


def test_with_nothing_played_the_second_does_not_play_first():
    decision = decide(_novelty_library(0.45), SessionSignals(context=_MID_ENERGY), rng=_never_explore())

    assert (_ids(decision), decision.second_plays_first) == (["c1", "c2", "c3"], False)


def test_the_margin_is_inclusive():
    """Equal scores are within a zero margin; only novelty decides."""
    last = _candidate("last", artist="X", genre="ambient", mood="calm")
    library = [_candidate("a", artist="Y", genre="ambient", mood="calm"), _candidate("b", artist="Z", genre="ambient", mood="dark")]

    decision = decide(library, SessionSignals(context=_AMBIENT, last_played=last), RecommendationPolicy(swap_margin=0.0), _never_explore())

    assert decision.picks[0].ranking_score == decision.picks[1].ranking_score
    assert (_ids(decision), decision.second_plays_first) == (["b", "a"], True)


def test_an_exploration_pick_in_second_place_does_not_play_first():
    """With a two-track queue the exploration pick is #2. It scores the same as #1 and is more novel,
    so an ordinary #2 would play first; an exploration pick never does."""
    last = _candidate("last", artist="X", genre="ambient", mood="calm")
    library = [
        _candidate("c1", artist="Y", genre="ambient", mood="calm"),
        _candidate("c2", artist="Z", genre="ambient", mood="calm"),
        _candidate("e", artist="E", genre="ambient", mood="dark"),
    ]

    decision = decide(library, SessionSignals(context=_AMBIENT, last_played=last), RecommendationPolicy(queue_size=2), _always_explore())

    assert decision.explored and _pick(decision, "e").is_exploration
    assert _pick(decision, "e").ranking_score == _pick(decision, "c1").ranking_score
    assert (_ids(decision), decision.second_plays_first) == (["c1", "e"], False)


def test_a_queue_that_is_not_full_is_not_explored():
    decision = decide([_candidate("c1", energy=0.5), _candidate("c2", energy=0.9)], SessionSignals(context=_MID_ENERGY), rng=_always_explore())

    assert (_ids(decision), decision.explored) == (["c1", "c2"], False)


# --- The decision as canonical Recommendations --------------------------------------------------------------


def test_picks_become_recommendations_whose_score_is_the_combined_score():
    decision = decide([_candidate("a", genre="ambient"), _candidate("r", genre="rock")], SessionSignals(context=_AMBIENT), rng=_never_explore())

    first, second = decision.recommendations()

    assert (first.candidate.candidate_id, first.rank, second.rank) == ("a", 1, 2)
    assert first.score_breakdown.normalized_score == pytest.approx(_combined(1.0))
    assert second.score_breakdown.normalized_score == pytest.approx(_combined(0.0))
    assert [(component.feature_name, component.maximum_points) for component in first.score_breakdown.components] == [
        ("intent", pytest.approx(_INTENT_SHARE)), ("session", pytest.approx(_SESSION_SHARE))
    ]


# --- Library tracks as candidates -------------------------------------------------------------------------


def _track(status=TrackStatus.READY, **values):
    now = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    return Track(
        track_id="7d1f2b3c-4d5e-4c55-9e0a-3f2c4a8e1b7d",
        sha256="a" * 64,
        size_bytes=10,
        audio_format=AudioFormat.FLAC,
        status=status,
        original_filename="song.flac",
        created_at=now,
        updated_at=now,
        analysis_version="test@1" if status is TrackStatus.READY else None,
        **values,
    )


def test_a_library_track_becomes_a_candidate_with_only_the_values_it_has():
    track = _track(
        title="Song",
        artist="Artist",
        labels=(
            TrackLabel(LabelKind.GENRE, "rock", "tag", False),
            TrackLabel(LabelKind.GENRE, "ambient", "tag", True),
            TrackLabel(LabelKind.MOOD, "calm", "tag", False),
        ),
    )

    candidate = candidate_from_track(track)

    music = candidate.music
    assert (candidate.track_id, candidate.artist, candidate.available) == (track.track_id, "Artist", True)
    assert (music.title, music.creator, music.genre, music.mood) == ("Song", "Artist", "ambient", "calm")
    assert (music.energy, music.danceability, music.tempo_bpm, music.valence, music.acousticness) == (None,) * 5


def test_a_track_without_tags_keeps_its_unknown_artist_unknown():
    candidate = candidate_from_track(_track(status=TrackStatus.IMPORTED))

    assert (candidate.music.title, candidate.music.creator, candidate.artist) == ("song.flac", "Unknown artist", None)
    assert (candidate.music.genre, candidate.music.mood, candidate.available) == (None, None, True)


def test_a_track_whose_managed_file_is_missing_is_unavailable():
    assert not candidate_from_track(_track(status=TrackStatus.MISSING_MANAGED_FILE)).available
