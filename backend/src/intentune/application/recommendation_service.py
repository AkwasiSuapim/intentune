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
from src.intentune.ports.catalog import Catalog


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


def recommend_from_catalog(
    catalog: Catalog,
    profile: UserProfile,
    limit: int = 5,
) -> List[Recommendation]:
    """Produce recommendations for one profile using candidates from a catalog port.

    Depends only on the Catalog port, not any concrete adapter -- callers can
    inject a CsvCatalog, a future database or YouTube catalog, or an
    in-memory fake catalog for tests.
    """
    if not isinstance(catalog, Catalog):
        raise TypeError("catalog must implement the Catalog port (a list_candidates() method)")

    candidates = catalog.list_candidates()
    return recommend_music(candidates, profile, limit=limit)
