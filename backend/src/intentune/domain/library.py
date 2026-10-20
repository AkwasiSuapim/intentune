"""The managed local music library (Prototype 1, phase B2).

The listener registers source folders (D03). Intentune scans them, copies each
audio file it accepts into its own managed media library (D02), and records
one logical track per distinct content, identified by SHA-256 (D24).

This module holds the rules, with no filesystem, mutagen, or SQLAlchemy code:
which audio formats are allowed, what a safe source-relative path looks like,
how embedded tags become track metadata, and which states sources, source
files, and tracks may be in. Adapters do the I/O (src/intentune/adapters/,
src/intentune/persistence/); the application layer coordinates them
(src/intentune/application/library.py).

States, from spec §7:

- A **source file** is one file seen in a source folder. It is IMPORTED (its
  content is in the library), UNSUPPORTED (rejected for a reason that will not
  change while the file stays the same), FAILED (a read, write, or consistency
  problem worth retrying on the next scan), or MISSING (no longer at the source).
- A **track** is one distinct piece of content in managed media. B2 creates
  tracks as IMPORTED: playable, with basic metadata. B3's background analysis
  moves it to ANALYZING while its first analysis runs and to READY once
  analyzed (analysis_version names the analyzer). MISSING_MANAGED_FILE means
  its managed copy is gone. Every state except MISSING_MANAGED_FILE is playable.

Nothing here invents a value: a tag that is absent stays None (D21).
"""

import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Iterable, Optional, Sequence, Tuple

from src.intentune.domain.validation import (
    new_uuid,
    optional_text,
    optional_utc_datetime,
    require_canonical_uuid,
    require_non_negative_int,
    require_text,
    require_utc_datetime,
)

EMBEDDED_TAGS_SOURCE = "embedded_tags"
"""Provenance for labels read from a file's own tags (declared, not inferred)."""

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_YEAR_PREFIX = re.compile(r"^\s*(\d{4})")
_MAX_YEAR = 9999


class AudioFormat(str, Enum):
    """The allowlisted audio formats (spec §27). The value is also the managed file's extension."""

    MP3 = "mp3"
    M4A = "m4a"
    FLAC = "flac"
    OGG = "ogg"
    OPUS = "opus"
    WAV = "wav"

    @property
    def extension(self) -> str:
        return self.value

    @classmethod
    def from_filename(cls, filename: str) -> Optional["AudioFormat"]:
        """The format a file name's extension claims, or None if it is not allowlisted.

        The claim is only a filter; the audio inspector confirms the content.
        """
        name = filename.rsplit("/", 1)[-1]
        stem, dot, extension = name.rpartition(".")
        if not dot or not stem:
            return None
        try:
            return cls(extension.lower())
        except ValueError:
            return None


class SourceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MISSING = "MISSING"


class SourceFileStatus(str, Enum):
    IMPORTED = "IMPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"
    MISSING = "MISSING"


class FailureReason(str, Enum):
    """Why a source file was not imported. FILE_TOO_LARGE and UNSUPPORTED_FORMAT are UNSUPPORTED; the rest FAILED."""

    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    IO_ERROR = "IO_ERROR"
    CHANGED_DURING_IMPORT = "CHANGED_DURING_IMPORT"


class TrackStatus(str, Enum):
    IMPORTED = "IMPORTED"
    ANALYZING = "ANALYZING"
    READY = "READY"
    MISSING_MANAGED_FILE = "MISSING_MANAGED_FILE"


class LabelKind(str, Enum):
    GENRE = "genre"
    MOOD = "mood"


# --- Errors ----------------------------------------------------------------------


class LibraryError(Exception):
    """Base class for library errors the application layer reports to its callers."""


class InvalidLibrarySource(LibraryError, ValueError):
    """The path given as a source folder cannot be used as one."""


class LibrarySourceNotFound(LibraryError, LookupError):
    pass


class TrackNotFound(LibraryError, LookupError):
    pass


class UnsupportedAudioFile(LibraryError):
    """The file is not a valid file of an allowlisted format."""

    def __init__(self, message: str, reason: FailureReason = FailureReason.UNSUPPORTED_FORMAT) -> None:
        super().__init__(message)
        self.reason = reason


class ManagedCopyMismatch(LibraryError):
    """The bytes copied into managed media do not match the hash computed before copying."""


class TagReadError(LibraryError):
    """A file's embedded tags could not be read. The track stays playable without them."""


# --- Rules -------------------------------------------------------------------------


def require_relative_path(value: object, field_name: str = "relative_path") -> str:
    """Require a POSIX path relative to a source root that cannot point outside it.

    Rejects absolute paths, drive letters, backslashes, NUL bytes, and empty,
    '.', or '..' segments.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if "\\" in value or "\x00" in value:
        raise ValueError(f"{field_name} must use '/' separators and contain no NUL bytes")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ValueError(f"{field_name} must be relative")
    if any(segment in ("", ".", "..") for segment in value.split("/")):
        raise ValueError(f"{field_name} must not contain empty, '.', or '..' segments")
    return value


def require_sha256(value: object, field_name: str = "sha256") -> str:
    if not isinstance(value, str) or not _SHA256.match(value):
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")
    return value


def year_from_tag(value: str) -> Optional[int]:
    """The year a date tag starts with ('2019', '2019-05-03'), or None if it does not start with one."""
    match = _YEAR_PREFIX.match(value)
    if not match:
        return None
    year = int(match.group(1))
    return year if 1 <= year <= _MAX_YEAR else None


def split_genres(values: Iterable[str]) -> Tuple[str, ...]:
    """Genre tag values as distinct labels, in order.

    A value may hold several genres separated by ';' ('Rock; Indie'). Other
    separators are kept, because they appear inside real genre names
    ('Hip-Hop/Rap', 'Drum & Bass'). Duplicates are dropped case-insensitively.
    """
    genres = []
    seen = set()
    for value in values:
        for part in value.split(";"):
            cleaned = part.strip()
            if cleaned and cleaned.casefold() not in seen:
                seen.add(cleaned.casefold())
                genres.append(cleaned)
    return tuple(genres)


def _first_text(values: Sequence[str]) -> Optional[str]:
    return next((value.strip() for value in values if value and value.strip()), None)


# --- Values --------------------------------------------------------------------------


@dataclass(frozen=True)
class EmbeddedTags:
    """Basic metadata a file declares about itself. Absent tags stay None."""

    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    year: Optional[int] = None
    genres: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", optional_text(self.title, "title"))
        object.__setattr__(self, "artist", optional_text(self.artist, "artist"))
        object.__setattr__(self, "album", optional_text(self.album, "album"))
        object.__setattr__(self, "year", _optional_year(self.year))
        if isinstance(self.genres, str) or not all(isinstance(genre, str) for genre in self.genres):
            raise ValueError("genres must be a sequence of strings")
        object.__setattr__(self, "genres", split_genres(tuple(self.genres)))

    @classmethod
    def from_tag_values(
        cls,
        titles: Sequence[str] = (),
        artists: Sequence[str] = (),
        albums: Sequence[str] = (),
        dates: Sequence[str] = (),
        genres: Sequence[str] = (),
    ) -> "EmbeddedTags":
        """Build from raw tag values, which formats store as lists.

        Title and album take the first non-blank value. Several artists are
        joined with ', '. The year comes from the first date that starts with one.
        """
        distinct_artists = []
        for artist in artists:
            cleaned = artist.strip() if artist else ""
            if cleaned and cleaned not in distinct_artists:
                distinct_artists.append(cleaned)
        year = next((year for year in (year_from_tag(date) for date in dates if date) if year is not None), None)
        return cls(
            title=_first_text(titles),
            artist=", ".join(distinct_artists) or None,
            album=_first_text(albums),
            year=year,
            genres=tuple(genres),
        )


def _optional_year(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= _MAX_YEAR:
        raise ValueError(f"year must be an integer from 1 to {_MAX_YEAR}")
    return value


def _optional_duration(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError("duration_seconds must be a non-negative number")
    return float(value)


@dataclass(frozen=True)
class AudioProbe:
    """What validating a file established: its confirmed format and, if the container states it, its duration."""

    audio_format: AudioFormat
    duration_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "audio_format", AudioFormat(self.audio_format))
        object.__setattr__(self, "duration_seconds", _optional_duration(self.duration_seconds))


@dataclass(frozen=True)
class DiscoveredFile:
    """One regular file found under a source folder during a scan."""

    relative_path: str
    size_bytes: int
    modified_ns: int

    def __post_init__(self) -> None:
        require_relative_path(self.relative_path)
        require_non_negative_int(self.size_bytes, "size_bytes")
        require_non_negative_int(self.modified_ns, "modified_ns")

    @property
    def filename(self) -> str:
        return self.relative_path.rsplit("/", 1)[-1]

    @property
    def audio_format(self) -> Optional[AudioFormat]:
        return AudioFormat.from_filename(self.filename)


# --- Entities ------------------------------------------------------------------------


@dataclass(frozen=True)
class LibrarySource:
    """A folder the listener registered. Several sources form one library (D03)."""

    source_id: str
    path: str
    status: SourceStatus
    created_at: datetime
    last_scanned_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        require_canonical_uuid(self.source_id, "source_id")
        object.__setattr__(self, "path", require_text(self.path, "path"))
        object.__setattr__(self, "status", SourceStatus(self.status))
        object.__setattr__(self, "created_at", require_utc_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "last_scanned_at", optional_utc_datetime(self.last_scanned_at, "last_scanned_at"))


def new_library_source(path: str, now: datetime) -> LibrarySource:
    return LibrarySource(source_id=new_uuid(), path=path, status=SourceStatus.ACTIVE, created_at=now)


@dataclass(frozen=True)
class SourceFile:
    """What the last scan recorded about one file in a source, so the next scan can skip unchanged files."""

    source_file_id: str
    source_id: str
    relative_path: str
    size_bytes: int
    modified_ns: int
    status: SourceFileStatus
    created_at: datetime
    updated_at: datetime
    sha256: Optional[str] = None
    track_id: Optional[str] = None
    failure_reason: Optional[FailureReason] = None

    def __post_init__(self) -> None:
        require_canonical_uuid(self.source_file_id, "source_file_id")
        require_canonical_uuid(self.source_id, "source_id")
        require_relative_path(self.relative_path)
        require_non_negative_int(self.size_bytes, "size_bytes")
        require_non_negative_int(self.modified_ns, "modified_ns")
        object.__setattr__(self, "status", SourceFileStatus(self.status))
        object.__setattr__(self, "created_at", require_utc_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", require_utc_datetime(self.updated_at, "updated_at"))
        if self.sha256 is not None:
            require_sha256(self.sha256)
        if self.track_id is not None:
            require_canonical_uuid(self.track_id, "track_id")
        if self.failure_reason is not None:
            object.__setattr__(self, "failure_reason", FailureReason(self.failure_reason))

        if self.status is SourceFileStatus.IMPORTED:
            if self.track_id is None or self.sha256 is None or self.failure_reason is not None:
                raise ValueError("an IMPORTED source file needs a track_id and sha256 and no failure_reason")
        if self.status in (SourceFileStatus.UNSUPPORTED, SourceFileStatus.FAILED) and self.failure_reason is None:
            raise ValueError(f"a {self.status.value} source file needs a failure_reason")

    def matches(self, discovered: DiscoveredFile) -> bool:
        """True when a newly discovered file has the size and modification time this record holds."""
        return self.size_bytes == discovered.size_bytes and self.modified_ns == discovered.modified_ns


@dataclass(frozen=True)
class TrackLabel:
    """One genre or mood label with its provenance (spec §9, D20)."""

    kind: LabelKind
    value: str
    source: str
    is_primary: bool
    confidence: Optional[float] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", LabelKind(self.kind))
        object.__setattr__(self, "value", require_text(self.value, "value"))
        object.__setattr__(self, "source", require_text(self.source, "source"))
        if not isinstance(self.is_primary, bool):
            raise ValueError("is_primary must be a bool")
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
                raise ValueError("confidence must be a number")
            if not 0.0 <= self.confidence <= 1.0:
                raise ValueError("confidence must be between 0.0 and 1.0")
            object.__setattr__(self, "confidence", float(self.confidence))


@dataclass(frozen=True)
class Track:
    """One distinct piece of content in the managed library."""

    track_id: str
    sha256: str
    size_bytes: int
    audio_format: AudioFormat
    status: TrackStatus
    original_filename: str
    created_at: datetime
    updated_at: datetime
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    year: Optional[int] = None
    duration_seconds: Optional[float] = None
    analysis_version: Optional[str] = None
    labels: Tuple[TrackLabel, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        require_canonical_uuid(self.track_id, "track_id")
        require_sha256(self.sha256)
        require_non_negative_int(self.size_bytes, "size_bytes")
        object.__setattr__(self, "audio_format", AudioFormat(self.audio_format))
        object.__setattr__(self, "status", TrackStatus(self.status))
        object.__setattr__(self, "original_filename", require_text(self.original_filename, "original_filename"))
        object.__setattr__(self, "created_at", require_utc_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", require_utc_datetime(self.updated_at, "updated_at"))
        object.__setattr__(self, "title", optional_text(self.title, "title"))
        object.__setattr__(self, "artist", optional_text(self.artist, "artist"))
        object.__setattr__(self, "album", optional_text(self.album, "album"))
        object.__setattr__(self, "year", _optional_year(self.year))
        object.__setattr__(self, "duration_seconds", _optional_duration(self.duration_seconds))
        object.__setattr__(self, "analysis_version", optional_text(self.analysis_version, "analysis_version"))

        labels = tuple(self.labels)
        if not all(isinstance(label, TrackLabel) for label in labels):
            raise ValueError("labels must contain only TrackLabel instances")
        for kind in LabelKind:
            if sum(1 for label in labels if label.kind is kind and label.is_primary) > 1:
                raise ValueError(f"a track has at most one primary {kind.value} label")
        object.__setattr__(self, "labels", labels)

    @property
    def genres(self) -> Tuple[str, ...]:
        """Genre label values, primary first."""
        genre_labels = [label for label in self.labels if label.kind is LabelKind.GENRE]
        return tuple(label.value for label in sorted(genre_labels, key=lambda label: not label.is_primary))

    def with_embedded_tags(self, tags: EmbeddedTags, now: datetime) -> "Track":
        """This track with its basic metadata and declared genres taken from embedded tags.

        In B2 embedded tags are the only source of title, artist, album, and year,
        so they replace those fields outright (an absent tag clears the field).
        Earlier embedded-tag labels are replaced. Labels from other sources are
        kept, and the first declared genre is primary only if no other primary
        genre exists.
        """
        kept = tuple(label for label in self.labels if label.source != EMBEDDED_TAGS_SOURCE)
        has_primary_genre = any(label.kind is LabelKind.GENRE and label.is_primary for label in kept)
        declared = tuple(
            TrackLabel(
                kind=LabelKind.GENRE,
                value=genre,
                source=EMBEDDED_TAGS_SOURCE,
                is_primary=index == 0 and not has_primary_genre,
            )
            for index, genre in enumerate(tags.genres)
        )
        return replace(
            self,
            title=tags.title,
            artist=tags.artist,
            album=tags.album,
            year=tags.year,
            labels=kept + declared,
            updated_at=now,
        )

    def with_status(self, status: TrackStatus, now: datetime) -> "Track":
        return replace(self, status=status, updated_at=now)

    @property
    def available_status(self) -> TrackStatus:
        """The status this track has whenever its managed copy is present: READY if analyzed, else IMPORTED."""
        return TrackStatus.READY if self.analysis_version is not None else TrackStatus.IMPORTED

    def with_analysis(self, analysis_version: str, now: datetime) -> "Track":
        """This track analyzed by analysis_version. A track whose managed copy is missing stays MISSING_MANAGED_FILE."""
        status = self.status if self.status is TrackStatus.MISSING_MANAGED_FILE else TrackStatus.READY
        return replace(self, status=status, analysis_version=analysis_version, updated_at=now)


def new_track_id() -> str:
    """A generated identity for a new track; also its managed file's name (never the source file name)."""
    return new_uuid()


@dataclass(frozen=True)
class ScanReport:
    """What one scan of one source did. Counts are files, except imported (new tracks) and repaired (tracks)."""

    source_id: str
    source_missing: bool = False
    imported: int = 0
    duplicates: int = 0
    unchanged: int = 0
    repaired: int = 0
    unsupported: int = 0
    failed: int = 0
    missing: int = 0
    ignored: int = 0
    tag_failures: int = 0
