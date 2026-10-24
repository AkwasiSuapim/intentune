"""Library storage ports: sources, the files seen in them, and tracks.

Implemented over SQLite in src/intentune/persistence/repositories.py. Like
every repository, these stage changes; the unit of work that owns them
commits (ports/unit_of_work.py). They accept and return domain models only.
"""

from typing import Iterable, List, Optional, Protocol, Set

from src.intentune.domain.library import LibrarySource, SourceFile, Track, TrackStatus


class LibrarySourceRepository(Protocol):
    def get(self, source_id: str) -> Optional[LibrarySource]:
        ...

    def get_by_path(self, path: str) -> Optional[LibrarySource]:
        """The source registered for exactly this normalized folder path, if any."""
        ...

    def list_all(self) -> List[LibrarySource]:
        """Every source, oldest first."""
        ...

    def add(self, source: LibrarySource) -> None:
        ...

    def save(self, source: LibrarySource) -> None:
        """Stage changes to an existing source."""
        ...


class SourceFileRepository(Protocol):
    def list_for_source(self, source_id: str) -> List[SourceFile]:
        """Everything recorded about the files of one source, by relative path."""
        ...

    def add(self, source_file: SourceFile) -> None:
        ...

    def save(self, source_file: SourceFile) -> None:
        ...


class TrackRepository(Protocol):
    def get(self, track_id: str) -> Optional[Track]:
        ...

    def get_by_sha256(self, sha256: str) -> Optional[Track]:
        """The track holding exactly this content, if the library has it (D24)."""
        ...

    def list_all(self) -> List[Track]:
        """Every track, in import order."""
        ...

    def get_many(self, track_ids: Iterable[str]) -> List[Track]:
        """The tracks with these ids, in import order. Ids of no track are left out (B11: one read, not one per id)."""
        ...

    def ids_with_status(self, status: TrackStatus) -> Set[str]:
        ...

    def add(self, track: Track) -> None:
        """Stage a new track together with its labels."""
        ...

    def save(self, track: Track) -> None:
        """Stage changes to an existing track. Its labels are replaced by track.labels."""
        ...
