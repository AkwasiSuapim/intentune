"""Application use cases for the managed local library (Prototype 1, phase B2).

Capabilities (execution guide §5): register a source, list sources, scan a
source (and rescan them all), import one discovered file, list tracks, get a
track, and mark a track unavailable.

Import pipeline for one file, in the guide's order:

    validate (allowlisted format, size limit, content confirms the format)
    -> hash (SHA-256)
    -> dedupe (same content already in the library? link to that track)
    -> copy into managed media as <track_uuid>.<extension>, verified by hash
    -> persist the track (IMPORTED: playable) and the source-file record
    -> extract basic tags from the managed copy
    -> deeper analysis: AnalysisService.enqueue_pending() (application/analysis.py)
       queues every track the current analyzer has not analyzed, so this
       module does not queue jobs itself.

Incremental scan rules (spec §5):

    unchanged (same size and mtime)  -> no work
    new                              -> import
    changed                          -> re-hash; import only if the content changed
    missing from the source          -> file marked MISSING; the managed copy stays usable
    source folder missing            -> source marked MISSING; its tracks stay usable
    exact duplicate                  -> no second logical track

A file that previously FAILED is retried even if unchanged; one that is
UNSUPPORTED is not, until it changes. A track whose managed copy is missing is
repaired when a source file with the same content is scanned again.

Each file is processed in its own short transactions, so one bad file never
undoes the others and SQLite's single writer is never held for long. One
failure never stops the scan (spec §7); failures are recorded and counted.

Everything here goes through ports. This module performs no file I/O.
"""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

from src.intentune.domain.library import (
    DiscoveredFile,
    FailureReason,
    InvalidLibrarySource,
    LibrarySource,
    LibrarySourceNotFound,
    ManagedCopyMismatch,
    ScanReport,
    SourceFile,
    SourceFileStatus,
    SourceStatus,
    TagReadError,
    Track,
    TrackNotFound,
    TrackStatus,
    UnsupportedAudioFile,
    new_library_source,
    new_track_id,
)
from src.intentune.domain.validation import new_uuid
from src.intentune.ports.library_files import AudioInspector, ManagedMedia, SourceFolders
from src.intentune.ports.unit_of_work import UnitOfWork

_DEFAULT_MAX_FILE_BYTES = 1024 ** 3


@dataclass(frozen=True)
class LibraryPolicy:
    """Import limits. 1 GiB per file by default, enough for long lossless recordings."""

    max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES

    def __post_init__(self) -> None:
        if isinstance(self.max_file_bytes, bool) or not isinstance(self.max_file_bytes, int) or self.max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be a positive integer")


class ImportOutcome(str, Enum):
    IMPORTED = "imported"
    DUPLICATE = "duplicates"
    UNCHANGED = "unchanged"
    REPAIRED = "repaired"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass(frozen=True)
class ImportResult:
    """What processing one discovered file did. track_id is the library track the file now maps to, if any."""

    outcome: ImportOutcome
    track_id: Optional[str] = None
    tags_read: bool = True


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LibraryService:
    def __init__(
        self,
        unit_of_work: UnitOfWork,
        folders: SourceFolders,
        inspector: AudioInspector,
        media: ManagedMedia,
        policy: LibraryPolicy = LibraryPolicy(),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._uow = unit_of_work
        self._folders = folders
        self._inspector = inspector
        self._media = media
        self._policy = policy
        self._clock = clock

    # --- Sources ------------------------------------------------------------------

    def register_source(self, path: str) -> LibrarySource:
        """Register a folder as a library source. Registering the same folder again returns the existing source.

        Adding a source never replaces earlier ones (D03). Registering does not scan.
        """
        root = self._folders.resolve_directory(path)
        if root is None:
            raise InvalidLibrarySource("The path is not an existing folder Intentune can scan.")
        with self._uow:
            existing = self._uow.library_sources.get_by_path(root)
            if existing is not None:
                return existing
            source = new_library_source(root, self._clock())
            self._uow.library_sources.add(source)
            self._uow.commit()
            return source

    def list_sources(self) -> List[LibrarySource]:
        with self._uow:
            return self._uow.library_sources.list_all()

    # --- Scanning -----------------------------------------------------------------

    def scan_source(self, source_id: str) -> ScanReport:
        """Incrementally scan one source and import what is new or changed."""
        with self._uow:
            source = self._require_source(source_id)
            known: Dict[str, SourceFile] = {
                source_file.relative_path: source_file
                for source_file in self._uow.source_files.list_for_source(source_id)
            }
            unavailable = self._uow.tracks.ids_with_status(TrackStatus.MISSING_MANAGED_FILE)

        root = self._folders.resolve_directory(source.path)
        if root is None:
            self._save_source(replace(source, status=SourceStatus.MISSING, last_scanned_at=self._clock()))
            return ScanReport(source_id=source_id, source_missing=True)

        counts: Counter = Counter()
        seen: Set[str] = set()
        for discovered in self._folders.list_files(root):
            if discovered.audio_format is None:
                counts["ignored"] += 1
                continue
            seen.add(discovered.relative_path)
            result = self._process(source, root, discovered, known.get(discovered.relative_path), unavailable)
            counts[result.outcome.value] += 1
            if not result.tags_read:
                counts["tag_failures"] += 1

        now = self._clock()
        vanished = [
            source_file
            for relative_path, source_file in known.items()
            if relative_path not in seen and source_file.status is not SourceFileStatus.MISSING
        ]
        with self._uow:
            for source_file in vanished:
                self._uow.source_files.save(replace(source_file, status=SourceFileStatus.MISSING, updated_at=now))
            self._uow.library_sources.save(replace(source, status=SourceStatus.ACTIVE, last_scanned_at=now))
            self._uow.commit()
        counts["missing"] += len(vanished)
        return ScanReport(source_id=source_id, **counts)

    def rescan_library(self) -> List[ScanReport]:
        """Scan every registered source: the manual Rescan Library action, and later the startup scan (D25)."""
        return [self.scan_source(source.source_id) for source in self.list_sources()]

    def import_file(self, source_id: str, discovered: DiscoveredFile) -> ImportResult:
        """Run the import pipeline for one file of a registered source (used by scans; B3's import jobs later)."""
        if discovered.audio_format is None:
            raise UnsupportedAudioFile("The file does not have an allowlisted audio extension.")
        with self._uow:
            source = self._require_source(source_id)
            previous = next(
                (
                    source_file
                    for source_file in self._uow.source_files.list_for_source(source_id)
                    if source_file.relative_path == discovered.relative_path
                ),
                None,
            )
            unavailable = self._uow.tracks.ids_with_status(TrackStatus.MISSING_MANAGED_FILE)
        root = self._folders.resolve_directory(source.path)
        if root is None:
            raise InvalidLibrarySource("The source folder is missing.")
        return self._process(source, root, discovered, previous, unavailable)

    # --- Tracks -------------------------------------------------------------------

    def list_tracks(self) -> List[Track]:
        with self._uow:
            return self._uow.tracks.list_all()

    def get_track(self, track_id: str) -> Track:
        with self._uow:
            track = self._uow.tracks.get(track_id)
        if track is None:
            raise TrackNotFound(track_id)
        return track

    def mark_track_unavailable(self, track_id: str) -> Track:
        """Record that a track's managed copy is missing. A later scan restores it if the content is found again."""
        with self._uow:
            track = self._uow.tracks.get(track_id)
            if track is None:
                raise TrackNotFound(track_id)
            if track.status is TrackStatus.MISSING_MANAGED_FILE:
                return track
            unavailable = track.with_status(TrackStatus.MISSING_MANAGED_FILE, self._clock())
            self._uow.tracks.save(unavailable)
            self._uow.commit()
            return unavailable

    # --- Pipeline -----------------------------------------------------------------

    def _process(
        self,
        source: LibrarySource,
        root: str,
        discovered: DiscoveredFile,
        previous: Optional[SourceFile],
        unavailable_track_ids: Set[str],
    ) -> ImportResult:
        if previous is not None and previous.matches(discovered):
            if previous.status is SourceFileStatus.UNSUPPORTED:
                return ImportResult(ImportOutcome.UNCHANGED)
            if previous.status is SourceFileStatus.IMPORTED and previous.track_id not in unavailable_track_ids:
                return ImportResult(ImportOutcome.UNCHANGED, previous.track_id)
        return self._import(source, root, discovered, previous)

    def _import(
        self,
        source: LibrarySource,
        root: str,
        discovered: DiscoveredFile,
        previous: Optional[SourceFile],
    ) -> ImportResult:
        audio_format = discovered.audio_format
        path = self._folders.file_path(root, discovered.relative_path)

        # Validate, then hash.
        if discovered.size_bytes > self._policy.max_file_bytes:
            return self._reject(source, discovered, previous, SourceFileStatus.UNSUPPORTED, FailureReason.FILE_TOO_LARGE)
        try:
            probe = self._inspector.probe(path, audio_format)
            sha256 = self._folders.sha256(path)
        except UnsupportedAudioFile as error:
            return self._reject(source, discovered, previous, SourceFileStatus.UNSUPPORTED, error.reason)
        except OSError:
            return self._reject(source, discovered, previous, SourceFileStatus.FAILED, FailureReason.IO_ERROR)

        # Dedupe.
        with self._uow:
            existing = self._uow.tracks.get_by_sha256(sha256)
        if existing is not None:
            return self._link_existing(source, path, discovered, previous, existing, sha256)

        # Copy into managed media, then persist.
        track_id = new_track_id()
        try:
            size_bytes = self._media.store(path, track_id, audio_format, sha256)
        except ManagedCopyMismatch:
            return self._reject(source, discovered, previous, SourceFileStatus.FAILED, FailureReason.CHANGED_DURING_IMPORT)
        except OSError:
            return self._reject(source, discovered, previous, SourceFileStatus.FAILED, FailureReason.IO_ERROR)

        now = self._clock()
        track = Track(
            track_id=track_id,
            sha256=sha256,
            size_bytes=size_bytes,
            audio_format=audio_format,
            status=TrackStatus.IMPORTED,
            original_filename=discovered.filename,
            created_at=now,
            updated_at=now,
            duration_seconds=probe.duration_seconds,
        )
        try:
            with self._uow:
                self._uow.tracks.add(track)
                self._stage_source_file(source, discovered, previous, SourceFileStatus.IMPORTED, now, sha256=sha256, track_id=track_id)
                self._uow.commit()
        except BaseException:
            self._media.discard(track_id, audio_format)
            raise

        # Extract basic tags. The track is already playable if this fails.
        return ImportResult(ImportOutcome.IMPORTED, track_id, tags_read=self._apply_embedded_tags(track))

    def _link_existing(
        self,
        source: LibrarySource,
        path: str,
        discovered: DiscoveredFile,
        previous: Optional[SourceFile],
        existing: Track,
        sha256: str,
    ) -> ImportResult:
        """The content is already in the library: record this file as another copy of it, repairing if needed."""
        outcome = ImportOutcome.UNCHANGED if previous is not None and previous.track_id == existing.track_id else ImportOutcome.DUPLICATE
        restored = None
        if existing.status is TrackStatus.MISSING_MANAGED_FILE:
            try:
                self._media.store(path, existing.track_id, existing.audio_format, sha256)
            except ManagedCopyMismatch:
                return self._reject(source, discovered, previous, SourceFileStatus.FAILED, FailureReason.CHANGED_DURING_IMPORT)
            except OSError:
                return self._reject(source, discovered, previous, SourceFileStatus.FAILED, FailureReason.IO_ERROR)
            restored = existing.with_status(existing.available_status, self._clock())
            outcome = ImportOutcome.REPAIRED

        now = self._clock()
        with self._uow:
            if restored is not None:
                self._uow.tracks.save(restored)
            self._stage_source_file(source, discovered, previous, SourceFileStatus.IMPORTED, now, sha256=sha256, track_id=existing.track_id)
            self._uow.commit()
        return ImportResult(outcome, existing.track_id)

    def _reject(
        self,
        source: LibrarySource,
        discovered: DiscoveredFile,
        previous: Optional[SourceFile],
        status: SourceFileStatus,
        reason: FailureReason,
    ) -> ImportResult:
        with self._uow:
            self._stage_source_file(source, discovered, previous, status, self._clock(), failure_reason=reason)
            self._uow.commit()
        outcome = ImportOutcome.UNSUPPORTED if status is SourceFileStatus.UNSUPPORTED else ImportOutcome.FAILED
        return ImportResult(outcome)

    def _apply_embedded_tags(self, track: Track) -> bool:
        try:
            tags = self._inspector.read_tags(self._media.path(track.track_id, track.audio_format))
        except (TagReadError, OSError):
            return False
        with self._uow:
            current = self._uow.tracks.get(track.track_id)
            self._uow.tracks.save(current.with_embedded_tags(tags, self._clock()))
            self._uow.commit()
        return True

    # --- Helpers ------------------------------------------------------------------

    def _require_source(self, source_id: str) -> LibrarySource:
        source = self._uow.library_sources.get(source_id)
        if source is None:
            raise LibrarySourceNotFound(source_id)
        return source

    def _save_source(self, source: LibrarySource) -> None:
        with self._uow:
            self._uow.library_sources.save(source)
            self._uow.commit()

    def _stage_source_file(
        self,
        source: LibrarySource,
        discovered: DiscoveredFile,
        previous: Optional[SourceFile],
        status: SourceFileStatus,
        now: datetime,
        sha256: Optional[str] = None,
        track_id: Optional[str] = None,
        failure_reason: Optional[FailureReason] = None,
    ) -> None:
        """Stage the record of what happened to this file, inside the caller's transaction."""
        if previous is None:
            self._uow.source_files.add(
                SourceFile(
                    source_file_id=new_uuid(),
                    source_id=source.source_id,
                    relative_path=discovered.relative_path,
                    size_bytes=discovered.size_bytes,
                    modified_ns=discovered.modified_ns,
                    status=status,
                    created_at=now,
                    updated_at=now,
                    sha256=sha256,
                    track_id=track_id,
                    failure_reason=failure_reason,
                )
            )
        else:
            self._uow.source_files.save(
                replace(
                    previous,
                    size_bytes=discovered.size_bytes,
                    modified_ns=discovered.modified_ns,
                    status=status,
                    sha256=sha256,
                    track_id=track_id,
                    failure_reason=failure_reason,
                    updated_at=now,
                )
            )
