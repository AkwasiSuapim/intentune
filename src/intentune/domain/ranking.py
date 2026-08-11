"""Canonical ranking for Intentune's recommendation domain.

Scores every candidate with src/intentune/domain/scoring.py, sorts using the
current tie-breaking rule, and assigns ranks. This module knows nothing
about CSV, dictionaries, or any legacy shape -- see
src/intentune/adapters/csv_catalog.py and src/recommender.py for those
boundaries.
"""

from typing import List, Sequence

from src.intentune.domain.models import MusicCandidate, Recommendation, UserProfile
from src.intentune.domain.scoring import score_candidate


def rank_candidates(
    candidates: Sequence[MusicCandidate],
    profile: UserProfile,
    limit: int = 5,
) -> List[Recommendation]:
    """Score, sort, and rank candidates for one profile.

    Ordering: score descending, then title ascending (case-insensitive), then
    creator ascending (case-insensitive); ties beyond that keep the original
    candidate order (Python's sort is stable).
    """
    if not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if limit < 0:
        raise ValueError("limit cannot be negative")
    if limit == 0 or not candidates:
        return []

    scored = [(candidate, score_candidate(candidate, profile)) for candidate in candidates]

    ranked = sorted(
        scored,
        key=lambda pair: (-pair[1].total_score, pair[0].title.lower(), pair[0].creator.lower()),
    )

    top = ranked[:limit]
    return [
        Recommendation(candidate=candidate, score_breakdown=breakdown, rank=rank)
        for rank, (candidate, breakdown) in enumerate(top, start=1)
    ]
