"""Canonical scoring for Intentune's recommendation domain.

This module is the single source of truth for the current four-feature
scoring rule (genre, mood, energy, danceability). The legacy dictionary-based
`score_song()` in src/recommender.py delegates here after converting its
dict inputs into MusicCandidate/UserProfile, instead of keeping a second,
separately maintained scoring implementation.

The weights, the 0.5 similarity cutoff, and the reason wording are unchanged
from the original CodePath baseline. Tempo, valence, and acousticness are not
scored yet -- see docs/planning/development-phases.md, "Expanded and Configurable
Scoring Engine" for that future milestone.
"""

from src.intentune.domain.models import MusicCandidate, ScoreBreakdown, ScoreComponent, UserProfile

GENRE_WEIGHT = 3.0
MOOD_WEIGHT = 3.0
ENERGY_WEIGHT = 2.0
DANCEABILITY_WEIGHT = 2.0
MAX_SCORE = GENRE_WEIGHT + MOOD_WEIGHT + ENERGY_WEIGHT + DANCEABILITY_WEIGHT

_SIMILARITY_CUTOFF = 0.5


def _similarity_points(preferred_value: float, actual_value: float, weight: float) -> float:
    difference = abs(actual_value - preferred_value)
    if difference >= _SIMILARITY_CUTOFF:
        similarity = 0.0
    else:
        similarity = 1.0 - difference
    similarity = max(0.0, min(1.0, similarity))
    return similarity * weight


def score_candidate(candidate: MusicCandidate, profile: UserProfile) -> ScoreBreakdown:
    """Score one candidate against a profile using the current four-feature rule.

    Requires preferred genre(s)/mood(s)/energy/danceability on the profile and
    genre/mood/energy/danceability on the candidate. This phase does not
    implement missing-feature normalization (see docs/planning/development-phases.md),
    so a missing required value raises ValueError instead of inventing a
    score.
    """
    if not profile.preferred_genres:
        raise ValueError("profile.preferred_genres is required for scoring")
    if not profile.preferred_moods:
        raise ValueError("profile.preferred_moods is required for scoring")
    if profile.preferred_energy is None:
        raise ValueError("profile.preferred_energy is required for scoring")
    if profile.preferred_danceability is None:
        raise ValueError("profile.preferred_danceability is required for scoring")
    if candidate.genre is None:
        raise ValueError("candidate.genre is required for scoring")
    if candidate.mood is None:
        raise ValueError("candidate.mood is required for scoring")
    if candidate.energy is None:
        raise ValueError("candidate.energy is required for scoring")
    if candidate.danceability is None:
        raise ValueError("candidate.danceability is required for scoring")

    candidate_genre = candidate.genre.strip().lower()
    preferred_genres = {genre.strip().lower() for genre in profile.preferred_genres}
    if candidate_genre in preferred_genres:
        genre_component = ScoreComponent(
            feature_name="genre",
            points_earned=GENRE_WEIGHT,
            maximum_points=GENRE_WEIGHT,
            reason=f"genre match (+{GENRE_WEIGHT:.1f})",
        )
    else:
        genre_component = ScoreComponent(
            feature_name="genre",
            points_earned=0.0,
            maximum_points=GENRE_WEIGHT,
            reason="genre did not match (+0.0)",
        )

    candidate_mood = candidate.mood.strip().lower()
    preferred_moods = {mood.strip().lower() for mood in profile.preferred_moods}
    if candidate_mood in preferred_moods:
        mood_component = ScoreComponent(
            feature_name="mood",
            points_earned=MOOD_WEIGHT,
            maximum_points=MOOD_WEIGHT,
            reason=f"mood match (+{MOOD_WEIGHT:.1f})",
        )
    else:
        mood_component = ScoreComponent(
            feature_name="mood",
            points_earned=0.0,
            maximum_points=MOOD_WEIGHT,
            reason="mood did not match (+0.0)",
        )

    energy_points = _similarity_points(profile.preferred_energy, candidate.energy, ENERGY_WEIGHT)
    energy_component = ScoreComponent(
        feature_name="energy",
        points_earned=energy_points,
        maximum_points=ENERGY_WEIGHT,
        reason=f"energy similarity (+{energy_points:.2f})",
    )

    danceability_points = _similarity_points(profile.preferred_danceability, candidate.danceability, DANCEABILITY_WEIGHT)
    danceability_component = ScoreComponent(
        feature_name="danceability",
        points_earned=danceability_points,
        maximum_points=DANCEABILITY_WEIGHT,
        reason=f"danceability similarity (+{danceability_points:.2f})",
    )

    components = (genre_component, mood_component, energy_component, danceability_component)
    raw_total = sum(component.points_earned for component in components)
    raw_total = max(0.0, min(MAX_SCORE, raw_total))
    total_score = round(raw_total, 6)

    return ScoreBreakdown(total_score=total_score, maximum_score=MAX_SCORE, components=components)
