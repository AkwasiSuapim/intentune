"""Catalog port: the application layer's dependency for candidate retrieval.

Describes the one capability the application needs from a candidate source
-- returning canonical MusicCandidate objects -- without naming CSV files,
database tables, or the YouTube API. A CSV catalog, a future database
catalog, and a future YouTube catalog can each satisfy this port by
implementing list_candidates(); the application layer depends on this
Protocol, not on any one of them. See docs/architecture/architecture.md.
"""

from typing import Protocol, Sequence, runtime_checkable

from src.intentune.domain.models import MusicCandidate


@runtime_checkable
class Catalog(Protocol):
    """Source of MusicCandidate objects available for recommendation."""

    def list_candidates(self) -> Sequence[MusicCandidate]:
        """Return every candidate this catalog currently has available."""
        ...
