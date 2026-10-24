"""Application service: what the current library can act on (Prototype 1, phase B9).

IntentCapability is the one place that answers, from the library as it is
now, whether anything can be recommended (readiness) and whether each intent
dimension has usable data (genre, mood, energy, danceability, tempo, valence,
acousticness). Every entry point asks it:
- GET /listening/vocabulary reports its vocabulary and support, so Tune and
  the starters show what is usable;
- MessageService interprets typed words with its vocabulary;
- ListeningService checks every structured start and REFINE against it before
  anything is recorded, and typed words reach those same use cases.

So typed and structured intent meet the same rule:

    typed text -> interpret -> capability check -> use case
    structured control      -> capability check -> use case

A use case that checks an intent and then refreshes the queue reads the
library once (library()) and hands the same tracks to both, so one command
loads the library once (B11).

A library with no playable tracks is not ready (LibraryNotReady): nothing
starts, and no dimension is called unsupported for it. In a ready library, a
dimension without usable data is unavailable for now (IntentUnavailable). The
rule itself is the pure unavailable_dimensions() (domain/intent.py), over the
vocabulary this service reads from the library, so a dimension becomes usable
by itself once the library has the data. Nothing about the library's state
lives in the recommendation domain.
"""

from typing import List, Optional, Sequence

from src.intentune.domain.intent import (
    IntentUnavailable,
    LibraryNotReady,
    Vocabulary,
    unavailable_dimensions,
    vocabulary_from_tracks,
)
from src.intentune.domain.library import Track
from src.intentune.domain.models import ListeningContext
from src.intentune.ports.unit_of_work import UnitOfWork


class IntentCapability:
    def __init__(self, unit_of_work: UnitOfWork) -> None:
        self._uow = unit_of_work

    def library(self) -> List[Track]:
        """Every track as it is now: what vocabulary() reads, for a use case to hand on to its queue refresh."""
        with self._uow:
            return self._uow.tracks.list_all()

    def vocabulary(self, library: Optional[Sequence[Track]] = None) -> Vocabulary:
        """The library's genres and moods, its readiness, and what each dimension's data allows, from its tracks now.

        library is the tracks as the caller has just read them with library(); without it, they are read here.
        """
        return vocabulary_from_tracks(library if library is not None else self.library())

    def require_ready(self, vocabulary: Optional[Vocabulary] = None) -> Vocabulary:
        """The vocabulary, if the library is ready for recommendations; LibraryNotReady if nothing is playable."""
        vocabulary = vocabulary if vocabulary is not None else self.vocabulary()
        if not vocabulary.capability.ready:
            raise LibraryNotReady()
        return vocabulary

    def require(self, before: ListeningContext, after: ListeningContext, vocabulary: Optional[Vocabulary] = None) -> None:
        """Refuse an intent (after) the library cannot act on now: LibraryNotReady, or IntentUnavailable for its parts."""
        vocabulary = self.require_ready(vocabulary)
        unavailable = unavailable_dimensions(before, after, vocabulary)
        if unavailable:
            raise IntentUnavailable(unavailable, vocabulary.capability.usable)
