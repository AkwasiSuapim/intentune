"""Application-layer orchestration for producing recommendations.

Coordinates canonical scoring and ranking for one use case: given a
candidate list, a user profile, and a result limit, produce typed
recommendations. Contains no I/O -- no file reads, no printing, no HTTP, no
AI, no YouTube calls. Those concerns live in adapters (catalog reading) or
the legacy compatibility layer (CLI output), not here.
"""

from typing import List, Sequence

from src.intentune.domain.models import MusicCandidate, Recommendation, UserProfile
from src.intentune.domain.ranking import rank_candidates


def recommend_music(
    candidates: Sequence[MusicCandidate],
    profile: UserProfile,
    limit: int = 5,
) -> List[Recommendation]:
    """Score and rank candidates for one user profile, returning typed recommendations."""
    if not isinstance(profile, UserProfile):
        raise TypeError("profile must be a UserProfile")
    for candidate in candidates:
        if not isinstance(candidate, MusicCandidate):
            raise TypeError("candidates must contain only MusicCandidate instances")

    return rank_candidates(candidates, profile, limit=limit)
