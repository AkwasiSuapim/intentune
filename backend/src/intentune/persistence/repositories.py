"""SQLAlchemy repositories: implement the storage ports over ORM records.

A repository works inside a Session it is given and never commits; the unit
of work that created it owns the transaction (see unit_of_work.py). It
accepts and returns domain models only, so ORM records stay inside the
persistence package.
"""

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.intentune.domain.library import (
    LibrarySource,
    SourceFile,
    Track,
    TrackLabel,
    TrackStatus,
)
from src.intentune.domain.listener import ListenerProfile
from src.intentune.domain.validation import new_uuid
from src.intentune.persistence.models import (
    LibrarySourceRecord,
    ListenerProfileRecord,
    SourceFileRecord,
    TrackLabelRecord,
    TrackRecord,
)


def _listener_profile_from_record(record: ListenerProfileRecord) -> ListenerProfile:
    return ListenerProfile(
        listener_profile_id=record.id,
        is_default=record.is_default,
        created_at=record.created_at,
    )


class SqlAlchemyListenerProfileRepository:
    """ListenerProfileRepository port implementation (see ports/listener_profiles.py)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, listener_profile_id: str) -> Optional[ListenerProfile]:
        record = self._session.get(ListenerProfileRecord, listener_profile_id)
        return _listener_profile_from_record(record) if record is not None else None

    def get_default(self) -> Optional[ListenerProfile]:
        statement = select(ListenerProfileRecord).where(ListenerProfileRecord.is_default.is_(True))
        record = self._session.scalars(statement).one_or_none()
        return _listener_profile_from_record(record) if record is not None else None

    def add(self, profile: ListenerProfile) -> None:
        self._session.add(
            ListenerProfileRecord(
                id=profile.listener_profile_id,
                is_default=profile.is_default,
                created_at=profile.created_at,
            )
        )


# --- Managed library (B2) ---------------------------------------------------------
#
# The records declare no ORM relationships, so a flush has no dependency that
# orders a parent row (a source, a track) before child rows staged in the
# same transaction. With foreign keys enforced, add() therefore flushes a
# parent row immediately, before anything can reference it.


def _require_record(record, kind: str, record_id: str):
    if record is None:
        raise LookupError(f"No {kind} with id {record_id!r} to save")
    return record


def _library_source_from_record(record: LibrarySourceRecord) -> LibrarySource:
    return LibrarySource(
        source_id=record.id,
        path=record.path,
        status=record.status,
        created_at=record.created_at,
        last_scanned_at=record.last_scanned_at,
    )


class SqlAlchemyLibrarySourceRepository:
    """LibrarySourceRepository port implementation (see ports/library.py)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, source_id: str) -> Optional[LibrarySource]:
        record = self._session.get(LibrarySourceRecord, source_id)
        return _library_source_from_record(record) if record is not None else None

    def get_by_path(self, path: str) -> Optional[LibrarySource]:
        record = self._session.scalars(select(LibrarySourceRecord).where(LibrarySourceRecord.path == path)).one_or_none()
        return _library_source_from_record(record) if record is not None else None

    def list_all(self) -> List[LibrarySource]:
        statement = select(LibrarySourceRecord).order_by(LibrarySourceRecord.created_at, LibrarySourceRecord.id)
        return [_library_source_from_record(record) for record in self._session.scalars(statement)]

    def add(self, source: LibrarySource) -> None:
        self._session.add(
            LibrarySourceRecord(
                id=source.source_id,
                path=source.path,
                status=source.status.value,
                created_at=source.created_at,
                last_scanned_at=source.last_scanned_at,
            )
        )
        self._session.flush()

    def save(self, source: LibrarySource) -> None:
        record = _require_record(self._session.get(LibrarySourceRecord, source.source_id), "library source", source.source_id)
        record.path = source.path
        record.status = source.status.value
        record.last_scanned_at = source.last_scanned_at


def _source_file_from_record(record: SourceFileRecord) -> SourceFile:
    return SourceFile(
        source_file_id=record.id,
        source_id=record.source_id,
        relative_path=record.relative_path,
        size_bytes=record.size_bytes,
        modified_ns=record.modified_ns,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        sha256=record.sha256,
        track_id=record.track_id,
        failure_reason=record.failure_reason,
    )


def _apply_source_file(record: SourceFileRecord, source_file: SourceFile) -> None:
    record.relative_path = source_file.relative_path
    record.size_bytes = source_file.size_bytes
    record.modified_ns = source_file.modified_ns
    record.sha256 = source_file.sha256
    record.status = source_file.status.value
    record.failure_reason = source_file.failure_reason.value if source_file.failure_reason is not None else None
    record.track_id = source_file.track_id
    record.updated_at = source_file.updated_at


class SqlAlchemySourceFileRepository:
    """SourceFileRepository port implementation (see ports/library.py)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_source(self, source_id: str) -> List[SourceFile]:
        statement = (
            select(SourceFileRecord)
            .where(SourceFileRecord.source_id == source_id)
            .order_by(SourceFileRecord.relative_path)
        )
        return [_source_file_from_record(record) for record in self._session.scalars(statement)]

    def add(self, source_file: SourceFile) -> None:
        record = SourceFileRecord(
            id=source_file.source_file_id,
            source_id=source_file.source_id,
            created_at=source_file.created_at,
        )
        _apply_source_file(record, source_file)
        self._session.add(record)

    def save(self, source_file: SourceFile) -> None:
        record = _require_record(
            self._session.get(SourceFileRecord, source_file.source_file_id), "source file", source_file.source_file_id
        )
        _apply_source_file(record, source_file)


def _track_label_from_record(record: TrackLabelRecord) -> TrackLabel:
    return TrackLabel(
        kind=record.kind,
        value=record.value,
        source=record.source,
        is_primary=record.is_primary,
        confidence=record.confidence,
    )


def _track_from_record(record: TrackRecord, labels: Iterable[TrackLabel]) -> Track:
    return Track(
        track_id=record.id,
        sha256=record.sha256,
        size_bytes=record.size_bytes,
        audio_format=record.audio_format,
        status=record.status,
        original_filename=record.original_filename,
        created_at=record.created_at,
        updated_at=record.updated_at,
        title=record.title,
        artist=record.artist,
        album=record.album,
        year=record.year,
        duration_seconds=record.duration_seconds,
        analysis_version=record.analysis_version,
        labels=tuple(labels),
    )


def _apply_track(record: TrackRecord, track: Track) -> None:
    record.sha256 = track.sha256
    record.size_bytes = track.size_bytes
    record.audio_format = track.audio_format.value
    record.status = track.status.value
    record.original_filename = track.original_filename
    record.title = track.title
    record.artist = track.artist
    record.album = track.album
    record.year = track.year
    record.duration_seconds = track.duration_seconds
    record.analysis_version = track.analysis_version
    record.updated_at = track.updated_at


class SqlAlchemyTrackRepository:
    """TrackRepository port implementation (see ports/library.py). Labels are stored in track_labels."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, track_id: str) -> Optional[Track]:
        record = self._session.get(TrackRecord, track_id)
        return self._with_labels([record])[0] if record is not None else None

    def get_by_sha256(self, sha256: str) -> Optional[Track]:
        record = self._session.scalars(select(TrackRecord).where(TrackRecord.sha256 == sha256)).one_or_none()
        return self._with_labels([record])[0] if record is not None else None

    def list_all(self) -> List[Track]:
        records = list(self._session.scalars(select(TrackRecord).order_by(TrackRecord.created_at, TrackRecord.id)))
        return self._with_labels(records)

    def ids_with_status(self, status: TrackStatus) -> Set[str]:
        return set(self._session.scalars(select(TrackRecord.id).where(TrackRecord.status == TrackStatus(status).value)))

    def add(self, track: Track) -> None:
        record = TrackRecord(id=track.track_id, created_at=track.created_at)
        _apply_track(record, track)
        self._session.add(record)
        self._session.flush()
        self._add_labels(track)

    def save(self, track: Track) -> None:
        record = _require_record(self._session.get(TrackRecord, track.track_id), "track", track.track_id)
        _apply_track(record, track)
        self._session.execute(delete(TrackLabelRecord).where(TrackLabelRecord.track_id == track.track_id))
        self._add_labels(track)

    def _add_labels(self, track: Track) -> None:
        for label in track.labels:
            self._session.add(
                TrackLabelRecord(
                    id=new_uuid(),
                    track_id=track.track_id,
                    kind=label.kind.value,
                    value=label.value,
                    source=label.source,
                    confidence=label.confidence,
                    is_primary=label.is_primary,
                )
            )

    def _with_labels(self, records: List[TrackRecord]) -> List[Track]:
        """Convert track records, loading their labels in one query."""
        if not records:
            return []
        statement = select(TrackLabelRecord).order_by(
            TrackLabelRecord.kind, TrackLabelRecord.is_primary.desc(), TrackLabelRecord.value
        )
        if len(records) == 1:
            statement = statement.where(TrackLabelRecord.track_id == records[0].id)
        labels: Dict[str, List[TrackLabel]] = defaultdict(list)
        for label_record in self._session.scalars(statement):
            labels[label_record.track_id].append(_track_label_from_record(label_record))
        return [_track_from_record(record, labels[record.id]) for record in records]
