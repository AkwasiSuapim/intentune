import pytest

from src.intentune.domain.models import MusicCandidate, UserProfile
from src.intentune.domain.scoring import (
    DANCEABILITY_WEIGHT,
    ENERGY_WEIGHT,
    GENRE_WEIGHT,
    MAX_SCORE,
    MOOD_WEIGHT,
    score_candidate,
)
from src.recommender import score_song


def _candidate(**overrides):
    values = dict(candidate_id="1", title="T", creator="C", source="csv", genre="lofi", mood="focused", energy=0.40, danceability=0.30)
    values.update(overrides)
    return MusicCandidate(**values)


def _profile(**overrides):
    values = dict(preferred_genres=("lofi",), preferred_moods=("focused",), preferred_energy=0.40, preferred_danceability=0.30)
    values.update(overrides)
    return UserProfile(**values)


def test_perfect_match_score():
    breakdown = score_candidate(_candidate(), _profile())

    assert breakdown.total_score == pytest.approx(10.0)
    assert breakdown.maximum_score == pytest.approx(10.0)


def test_genre_mismatch_partial_score():
    breakdown = score_candidate(_candidate(genre="pop"), _profile())

    assert breakdown.total_score == pytest.approx(7.0)


def test_mood_mismatch_partial_score():
    breakdown = score_candidate(_candidate(mood="chill"), _profile())

    assert breakdown.total_score == pytest.approx(7.0)


def test_full_mismatch_zero_score():
    breakdown = score_candidate(
        _candidate(genre="pop", mood="chill", energy=0.90, danceability=0.90),
        _profile(),
    )

    assert breakdown.total_score == pytest.approx(0.0)


def test_cutoff_behavior_at_exactly_half_difference():
    breakdown = score_candidate(_candidate(energy=0.90), _profile(preferred_energy=0.40))
    energy_component = next(c for c in breakdown.components if c.feature_name == "energy")

    assert energy_component.points_earned == pytest.approx(0.0)


def test_cutoff_behavior_just_under_half_difference():
    breakdown = score_candidate(_candidate(energy=0.899), _profile(preferred_energy=0.40))
    energy_component = next(c for c in breakdown.components if c.feature_name == "energy")

    assert energy_component.points_earned > 0.0


def test_genre_reason_wording():
    breakdown = score_candidate(_candidate(), _profile())
    genre_component = next(c for c in breakdown.components if c.feature_name == "genre")

    assert genre_component.reason == "genre match (+3.0)"

    breakdown = score_candidate(_candidate(genre="pop"), _profile())
    genre_component = next(c for c in breakdown.components if c.feature_name == "genre")

    assert genre_component.reason == "genre did not match (+0.0)"


def test_mood_reason_wording():
    breakdown = score_candidate(_candidate(), _profile())
    mood_component = next(c for c in breakdown.components if c.feature_name == "mood")

    assert mood_component.reason == "mood match (+3.0)"

    breakdown = score_candidate(_candidate(mood="chill"), _profile())
    mood_component = next(c for c in breakdown.components if c.feature_name == "mood")

    assert mood_component.reason == "mood did not match (+0.0)"


def test_energy_reason_wording():
    breakdown = score_candidate(_candidate(), _profile())
    energy_component = next(c for c in breakdown.components if c.feature_name == "energy")

    assert energy_component.reason == "energy similarity (+2.00)"


def test_danceability_reason_wording():
    breakdown = score_candidate(_candidate(), _profile())
    danceability_component = next(c for c in breakdown.components if c.feature_name == "danceability")

    assert danceability_component.reason == "danceability similarity (+2.00)"


def test_weights_match_documented_values():
    assert GENRE_WEIGHT == 3.0
    assert MOOD_WEIGHT == 3.0
    assert ENERGY_WEIGHT == 2.0
    assert DANCEABILITY_WEIGHT == 2.0
    assert MAX_SCORE == 10.0


def test_missing_candidate_field_raises():
    candidate = MusicCandidate(candidate_id="1", title="T", creator="C", source="csv", genre="lofi", mood="focused", danceability=0.3)

    with pytest.raises(ValueError):
        score_candidate(candidate, _profile())


def test_missing_profile_field_raises():
    profile = UserProfile(preferred_genres=("lofi",), preferred_moods=("focused",), preferred_danceability=0.3)

    with pytest.raises(ValueError):
        score_candidate(_candidate(), profile)


@pytest.mark.parametrize(
    ("candidate_kwargs", "profile_kwargs"),
    [
        ({}, {}),
        ({"genre": "pop"}, {}),
        ({"mood": "chill"}, {}),
        ({"genre": "pop", "mood": "chill", "energy": 0.90, "danceability": 0.90}, {}),
    ],
)
def test_canonical_scoring_matches_legacy_score_song(candidate_kwargs, profile_kwargs):
    candidate = _candidate(**candidate_kwargs)
    profile = _profile(**profile_kwargs)

    breakdown = score_candidate(candidate, profile)

    legacy_user_prefs = {
        "favorite_genre": profile.preferred_genres[0],
        "favorite_mood": profile.preferred_moods[0],
        "preferred_energy": profile.preferred_energy,
        "preferred_danceability": profile.preferred_danceability,
    }
    legacy_song = {
        "genre": candidate.genre,
        "mood": candidate.mood,
        "energy": candidate.energy,
        "danceability": candidate.danceability,
    }
    legacy_score, legacy_reasons = score_song(legacy_user_prefs, legacy_song)

    assert breakdown.total_score == pytest.approx(legacy_score)
    assert [component.reason for component in breakdown.components] == legacy_reasons
