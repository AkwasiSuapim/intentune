"""SQLAlchemy repositories: implement the storage ports over ORM records.

A repository works inside a Session it is given and never commits; the unit
of work that created it owns the transaction (see unit_of_work.py). It
accepts and returns domain models only, so ORM records stay inside the
persistence package.
"""

import dataclasses
import json
import threading
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

from sqlalchemy import Row, delete, func, select, update
from sqlalchemy.orm import Session

from src.intentune.domain.adaptation import (
    CATEGORICAL_DIMENSIONS,
    EvidenceReference,
    LongTermProfile,
    ProfileAdjustment,
    ProfileDimension,
)
from src.intentune.domain.analysis import AnalysisJob, AnalysisJobKind, AnalysisJobStatus, TrackFeature
from src.intentune.domain.models import ListeningContext, UserProfile
from src.intentune.domain.session import (
    FeedbackEvent,
    ListeningSession,
    OccurrenceStatus,
    RecommendationOccurrence,
    SessionStatus,
    SessionTurn,
)
from src.intentune.domain.library import (
    LibrarySource,
    SourceFile,
    Track,
    TrackLabel,
    TrackStatus,
)
from src.intentune.domain.listener import ListenerProfile
from src.intentune.domain.playlist import Playlist, PlaylistItem
from src.intentune.domain.validation import new_uuid
from src.intentune.persistence.models import (
    AnalysisJobRecord,
    FeedbackEventRecord,
    LibraryRevisionRecord,
    LibrarySourceRecord,
    ListenerProfileRecord,
    LongTermAdjustmentEvidenceRecord,
    LongTermAdjustmentRecord,
    LongTermProfileRecord,
    ListeningSessionRecord,
    PlaylistItemRecord,
    PlaylistRecord,
    RecommendationOccurrenceRecord,
    SessionTurnRecord,
    SourceFileRecord,
    TrackFeatureRecord,
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


# The library is read as plain rows of these columns, not ORM records: building a record per track and label
# was most of a full read's cost (B11). A row and a record answer the same attribute names.
_TRACK_COLUMNS = tuple(getattr(TrackRecord, column.key) for column in TrackRecord.__table__.columns)
_LABEL_COLUMNS = tuple(getattr(TrackLabelRecord, column.key) for column in TrackLabelRecord.__table__.columns)
_TrackRow = Union[TrackRecord, Row]
# A listener's whole history is read as rows too: thousands of them for a long history (B11).
_TURN_COLUMNS = tuple(getattr(SessionTurnRecord, column.key) for column in SessionTurnRecord.__table__.columns)
_OCCURRENCE_COLUMNS = tuple(
    getattr(RecommendationOccurrenceRecord, column.key) for column in RecommendationOccurrenceRecord.__table__.columns
)
_EVENT_COLUMNS = tuple(getattr(FeedbackEventRecord, column.key) for column in FeedbackEventRecord.__table__.columns)
_IN_BATCH = 500  # ids per IN (...) list, well under SQLite's bound-parameter limit


def _track_label_from_record(record: Union[TrackLabelRecord, Row]) -> TrackLabel:
    return TrackLabel(
        kind=record.kind,
        value=record.value,
        source=record.source,
        is_primary=record.is_primary,
        confidence=record.confidence,
    )


def _track_from_record(record: _TrackRow, labels: Iterable[TrackLabel]) -> Track:
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


class TrackSnapshot:
    """The library's last full read, kept for the next one while the library revision is unchanged (B11, TD-022).

    The revision is an integer in library_revision. SqlAlchemyTrackRepository advances it, in the same transaction,
    with every write to a track or its labels, which is every change to what a Track holds: metadata, labels,
    status, availability. The invariants:

    - A read never returns a library older than a commit that finished before it began. The read takes the
      revision the database has committed, which every earlier commit has advanced, and returns kept tracks only
      when they were kept under exactly that revision.
    - Only committed states are kept. A transaction that has written tracks reads the library afresh and keeps
      nothing, so a rolled-back write neither publishes nor invalidates anything, and no uncommitted revision is
      ever kept.
    - Publication never goes backwards. keep() installs a read only if its revision is newer than the one kept,
      under a lock, so two overlapping reads that finish in reverse order cannot leave the older one installed.
      (Each kept value is an immutable tuple; tracks_for() reads it without the lock.)

    For future work: a write to anything else this snapshot comes to hold must advance the revision too. When
    measured features become part of what Policy v1 reads from the library, their writes
    (TrackFeatureRepository.replace_for_analyzer()) must advance it as track writes do.

    One per process (the API container).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._kept: Optional[Tuple[int, Tuple[Track, ...]]] = None

    @property
    def revision(self) -> Optional[int]:
        """The revision of the kept read; None before the first."""
        kept = self._kept
        return kept[0] if kept is not None else None

    def tracks_for(self, revision: int) -> Optional[Tuple[Track, ...]]:
        kept = self._kept
        return kept[1] if kept is not None and kept[0] == revision else None

    def keep(self, revision: int, tracks: Sequence[Track]) -> None:
        """Keep a read of the committed library at this revision, unless a newer read is already kept."""
        value = (revision, tuple(tracks))
        with self._lock:
            if self._kept is None or revision > self._kept[0]:
                self._kept = value


class SqlAlchemyTrackRepository:
    """TrackRepository port implementation (see ports/library.py). Labels are stored in track_labels.

    Every write advances the library revision, in the same transaction. With a TrackSnapshot, list_all() returns
    the kept full read while the revision is the one it was read under, and keeps reads of the committed library.
    """

    def __init__(self, session: Session, snapshot: Optional[TrackSnapshot] = None) -> None:
        self._session = session
        self._snapshot = snapshot
        self._wrote = False  # whether this session has written tracks: its reads are then its own, not the committed library

    def get(self, track_id: str) -> Optional[Track]:
        record = self._session.get(TrackRecord, track_id)
        return self._with_labels([record])[0] if record is not None else None

    def get_by_sha256(self, sha256: str) -> Optional[Track]:
        record = self._session.scalars(select(TrackRecord).where(TrackRecord.sha256 == sha256)).one_or_none()
        return self._with_labels([record])[0] if record is not None else None

    def list_all(self) -> List[Track]:
        revision = self._revision() if self._snapshot is not None and not self._wrote else None
        if revision is not None:
            kept = self._snapshot.tracks_for(revision)
            if kept is not None:
                return list(kept)
        rows = self._session.execute(select(*_TRACK_COLUMNS).order_by(TrackRecord.created_at, TrackRecord.id)).all()
        tracks = self._with_labels(rows, every_track=True)
        if revision is not None:
            self._snapshot.keep(revision, tracks)
        return tracks

    def get_many(self, track_ids: Iterable[str]) -> List[Track]:
        ids = sorted(set(track_ids))
        rows = []
        for start in range(0, len(ids), _IN_BATCH):
            rows.extend(self._session.execute(select(*_TRACK_COLUMNS).where(TrackRecord.id.in_(ids[start : start + _IN_BATCH]))))
        rows.sort(key=lambda row: (row.created_at, row.id))
        return self._with_labels(rows)

    def ids_with_status(self, status: TrackStatus) -> Set[str]:
        return set(self._session.scalars(select(TrackRecord.id).where(TrackRecord.status == TrackStatus(status).value)))

    def add(self, track: Track) -> None:
        record = TrackRecord(id=track.track_id, created_at=track.created_at)
        _apply_track(record, track)
        self._session.add(record)
        self._session.flush()
        self._add_labels(track)
        self._changed()

    def save(self, track: Track) -> None:
        record = _require_record(self._session.get(TrackRecord, track.track_id), "track", track.track_id)
        _apply_track(record, track)
        self._session.execute(delete(TrackLabelRecord).where(TrackLabelRecord.track_id == track.track_id))
        self._add_labels(track)
        self._changed()

    def _revision(self) -> Optional[int]:
        """The library's revision, as this transaction sees it. None if the database has none."""
        return self._session.scalar(select(LibraryRevisionRecord.revision).where(LibraryRevisionRecord.id == 1))

    def _changed(self) -> None:
        """Advance the library revision in this transaction, so no kept full read matches the library once it commits."""
        self._session.execute(
            update(LibraryRevisionRecord).where(LibraryRevisionRecord.id == 1).values(revision=LibraryRevisionRecord.revision + 1)
        )
        self._wrote = True

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

    def _with_labels(self, records: Sequence[_TrackRow], every_track: bool = False) -> List[Track]:
        """Convert track records or rows, loading their labels: every label at once for every_track, else by id."""
        if not records:
            return []
        statement = select(*_LABEL_COLUMNS).order_by(
            TrackLabelRecord.kind, TrackLabelRecord.is_primary.desc(), TrackLabelRecord.value
        )
        if every_track:
            statements = [statement]
        else:
            ids = [record.id for record in records]
            statements = [statement.where(TrackLabelRecord.track_id.in_(ids[start : start + _IN_BATCH])) for start in range(0, len(ids), _IN_BATCH)]
        labels: Dict[str, List[TrackLabel]] = defaultdict(list)
        for batch in statements:
            for label_row in self._session.execute(batch):
                labels[label_row.track_id].append(_track_label_from_record(label_row))
        return [_track_from_record(record, labels[record.id]) for record in records]


# --- Background analysis (B3) -----------------------------------------------------


def _analysis_job_from_record(record: AnalysisJobRecord) -> AnalysisJob:
    return AnalysisJob(
        job_id=record.id,
        track_id=record.track_id,
        kind=record.kind,
        analyzer=record.analyzer,
        status=record.status,
        attempts=record.attempts,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        failure_reason=record.failure_reason,
        error_message=record.error_message,
    )


def _apply_analysis_job(record: AnalysisJobRecord, job: AnalysisJob) -> None:
    record.status = job.status.value
    record.attempts = job.attempts
    record.failure_reason = job.failure_reason.value if job.failure_reason is not None else None
    record.error_message = job.error_message
    record.updated_at = job.updated_at
    record.started_at = job.started_at
    record.finished_at = job.finished_at


class SqlAlchemyAnalysisJobRepository:
    """AnalysisJobRepository port implementation (see ports/analysis.py)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, job_id: str) -> Optional[AnalysisJob]:
        record = self._session.get(AnalysisJobRecord, job_id)
        return _analysis_job_from_record(record) if record is not None else None

    def list_all(self, status: Optional[AnalysisJobStatus] = None) -> List[AnalysisJob]:
        statement = select(AnalysisJobRecord).order_by(AnalysisJobRecord.created_at, AnalysisJobRecord.id)
        if status is not None:
            statement = statement.where(AnalysisJobRecord.status == AnalysisJobStatus(status).value)
        return [_analysis_job_from_record(record) for record in self._session.scalars(statement)]

    def list_for_analyzer(self, kind: AnalysisJobKind, analyzer: str) -> List[AnalysisJob]:
        statement = (
            select(AnalysisJobRecord)
            .where(AnalysisJobRecord.kind == AnalysisJobKind(kind).value, AnalysisJobRecord.analyzer == analyzer)
            .order_by(AnalysisJobRecord.created_at, AnalysisJobRecord.id)
        )
        return [_analysis_job_from_record(record) for record in self._session.scalars(statement)]

    def add(self, job: AnalysisJob) -> None:
        record = AnalysisJobRecord(
            id=job.job_id,
            track_id=job.track_id,
            kind=job.kind.value,
            analyzer=job.analyzer,
            created_at=job.created_at,
        )
        _apply_analysis_job(record, job)
        self._session.add(record)

    def save(self, job: AnalysisJob) -> None:
        _apply_analysis_job(_require_record(self._session.get(AnalysisJobRecord, job.job_id), "analysis job", job.job_id), job)

    def claim_next(self, now: datetime) -> Optional[AnalysisJob]:
        """One UPDATE ... RETURNING: no other worker can claim the same job between the read and the write."""
        self._session.flush()
        oldest_pending = (
            select(AnalysisJobRecord.id)
            .where(AnalysisJobRecord.status == AnalysisJobStatus.PENDING.value)
            .order_by(AnalysisJobRecord.created_at, AnalysisJobRecord.id)
            .limit(1)
            .scalar_subquery()
        )
        statement = (
            update(AnalysisJobRecord)
            .where(AnalysisJobRecord.id == oldest_pending, AnalysisJobRecord.status == AnalysisJobStatus.PENDING.value)
            .values(
                status=AnalysisJobStatus.RUNNING.value,
                attempts=AnalysisJobRecord.attempts + 1,
                started_at=now,
                finished_at=None,
                failure_reason=None,
                error_message=None,
                updated_at=now,
            )
            .returning(AnalysisJobRecord.id)
            .execution_options(synchronize_session=False)
        )
        claimed_id = self._session.execute(statement).scalar_one_or_none()
        if claimed_id is None:
            return None
        record = self._session.get(AnalysisJobRecord, claimed_id, populate_existing=True)
        return _analysis_job_from_record(record)


def _track_feature_from_record(record: TrackFeatureRecord) -> TrackFeature:
    return TrackFeature(
        name=record.name,
        value=record.value,
        analyzer_name=record.analyzer_name,
        analyzer_version=record.analyzer_version,
        computed_at=record.computed_at,
        confidence=record.confidence,
    )


class SqlAlchemyTrackFeatureRepository:
    """TrackFeatureRepository port implementation (see ports/analysis.py)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_track(self, track_id: str) -> List[TrackFeature]:
        statement = select(TrackFeatureRecord).where(TrackFeatureRecord.track_id == track_id).order_by(TrackFeatureRecord.name)
        return [_track_feature_from_record(record) for record in self._session.scalars(statement)]

    def replace_for_analyzer(self, track_id: str, analyzer_name: str, features: Sequence[TrackFeature]) -> None:
        self._session.execute(
            delete(TrackFeatureRecord).where(
                TrackFeatureRecord.track_id == track_id, TrackFeatureRecord.analyzer_name == analyzer_name
            )
        )
        for feature in features:
            if feature.analyzer_name != analyzer_name:
                raise ValueError("every replacement feature must come from the analyzer being replaced")
            self._session.add(
                TrackFeatureRecord(
                    id=new_uuid(),
                    track_id=track_id,
                    name=feature.name.value,
                    value=feature.value,
                    analyzer_name=feature.analyzer_name,
                    analyzer_version=feature.analyzer_version,
                    confidence=feature.confidence,
                    computed_at=feature.computed_at,
                )
            )


# --- Listening sessions (B4) --------------------------------------------------------

_CONTEXT_FORMAT = 1
_CONTEXT_FIELDS = tuple(field.name for field in dataclasses.fields(ListeningContext))


def context_to_json(context: ListeningContext) -> str:
    """A ListeningContext as compact, key-sorted JSON tagged with its storage format."""
    values = {}
    for name in _CONTEXT_FIELDS:
        value = getattr(context, name)
        values[name] = list(value) if isinstance(value, tuple) else value
    return json.dumps({"format": _CONTEXT_FORMAT, "context": values}, sort_keys=True, separators=(",", ":"))


def context_from_json(text: str) -> ListeningContext:
    """The ListeningContext a stored JSON value describes. Unknown formats or fields are refused, not ignored."""
    payload = json.loads(text)
    if not isinstance(payload, dict) or payload.get("format") != _CONTEXT_FORMAT or not isinstance(payload.get("context"), dict):
        raise ValueError("stored listening context has an unknown format")
    unknown = set(payload["context"]) - set(_CONTEXT_FIELDS)
    if unknown:
        raise ValueError(f"stored listening context has unknown fields: {sorted(unknown)}")
    return ListeningContext(**payload["context"])


def _session_from_record(record: ListeningSessionRecord) -> ListeningSession:
    return ListeningSession(
        session_id=record.id,
        listener_profile_id=record.listener_profile_id,
        status=record.status,
        current_context=context_from_json(record.context_json),
        started_at=record.started_at,
        updated_at=record.updated_at,
        ended_at=record.ended_at,
        end_reason=record.end_reason,
    )


def _apply_session(record: ListeningSessionRecord, session: ListeningSession) -> None:
    record.status = session.status.value
    record.end_reason = session.end_reason.value if session.end_reason is not None else None
    record.context_json = context_to_json(session.current_context)
    record.updated_at = session.updated_at
    record.ended_at = session.ended_at


class SqlAlchemyListeningSessionRepository:
    """ListeningSessionRepository port implementation (see ports/sessions.py)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, session_id: str) -> Optional[ListeningSession]:
        record = self._session.get(ListeningSessionRecord, session_id)
        return _session_from_record(record) if record is not None else None

    def get_active_for_listener(self, listener_profile_id: str) -> Optional[ListeningSession]:
        statement = select(ListeningSessionRecord).where(
            ListeningSessionRecord.listener_profile_id == listener_profile_id,
            ListeningSessionRecord.status == SessionStatus.ACTIVE.value,
        )
        record = self._session.scalars(statement).one_or_none()
        return _session_from_record(record) if record is not None else None

    def list_for_listener(self, listener_profile_id: str) -> List[ListeningSession]:
        statement = (
            select(ListeningSessionRecord)
            .where(ListeningSessionRecord.listener_profile_id == listener_profile_id)
            .order_by(ListeningSessionRecord.started_at.desc(), ListeningSessionRecord.id)
        )
        return [_session_from_record(record) for record in self._session.scalars(statement)]

    def list_active(self) -> List[ListeningSession]:
        statement = (
            select(ListeningSessionRecord)
            .where(ListeningSessionRecord.status == SessionStatus.ACTIVE.value)
            .order_by(ListeningSessionRecord.started_at, ListeningSessionRecord.id)
        )
        return [_session_from_record(record) for record in self._session.scalars(statement)]

    def add(self, session: ListeningSession) -> None:
        record = ListeningSessionRecord(
            id=session.session_id, listener_profile_id=session.listener_profile_id, started_at=session.started_at
        )
        _apply_session(record, session)
        self._session.add(record)
        self._session.flush()

    def save(self, session: ListeningSession) -> None:
        record = _require_record(self._session.get(ListeningSessionRecord, session.session_id), "session", session.session_id)
        _apply_session(record, session)
        self._session.flush()


def _turn_from_record(record: SessionTurnRecord) -> SessionTurn:
    return SessionTurn(
        turn_id=record.id,
        session_id=record.session_id,
        sequence=record.sequence,
        kind=record.kind,
        context=context_from_json(record.context_json),
        created_at=record.created_at,
        occurrence_id=record.occurrence_id,
    )


class SqlAlchemySessionTurnRepository:
    """SessionTurnRepository port implementation (see ports/sessions.py). Turns are history: added, never changed."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_session(self, session_id: str) -> List[SessionTurn]:
        statement = select(SessionTurnRecord).where(SessionTurnRecord.session_id == session_id).order_by(SessionTurnRecord.sequence)
        return [_turn_from_record(record) for record in self._session.scalars(statement)]

    def list_for_listener(self, listener_profile_id: str) -> List[SessionTurn]:
        statement = (
            select(*_TURN_COLUMNS)
            .join(ListeningSessionRecord, ListeningSessionRecord.id == SessionTurnRecord.session_id)
            .where(ListeningSessionRecord.listener_profile_id == listener_profile_id)
            .order_by(SessionTurnRecord.session_id, SessionTurnRecord.sequence)
        )
        return [_turn_from_record(row) for row in self._session.execute(statement)]

    def add(self, turn: SessionTurn) -> None:
        self._session.add(
            SessionTurnRecord(
                id=turn.turn_id,
                session_id=turn.session_id,
                sequence=turn.sequence,
                kind=turn.kind.value,
                context_json=context_to_json(turn.context),
                occurrence_id=turn.occurrence_id,
                created_at=turn.created_at,
            )
        )
        self._session.flush()


def _occurrence_from_record(record: RecommendationOccurrenceRecord) -> RecommendationOccurrence:
    return RecommendationOccurrence(
        occurrence_id=record.id,
        session_id=record.session_id,
        track_id=record.track_id,
        rank=record.rank,
        algorithm=record.algorithm,
        status=record.status,
        surfaced_at=record.surfaced_at,
        updated_at=record.updated_at,
        surfaced_position=record.surfaced_position,
        score=record.score,
        queue_position=record.queue_position,
        started_at=record.started_at,
        finished_at=record.finished_at,
        is_exploration=record.is_exploration,
    )


def _apply_occurrence(record: RecommendationOccurrenceRecord, occurrence: RecommendationOccurrence) -> None:
    record.status = occurrence.status.value
    record.queue_position = occurrence.queue_position
    record.updated_at = occurrence.updated_at
    record.started_at = occurrence.started_at
    record.finished_at = occurrence.finished_at


class SqlAlchemyRecommendationOccurrenceRepository:
    """RecommendationOccurrenceRepository port implementation (see ports/sessions.py).

    add() and save() flush at once, so the order of the caller's changes is the
    order of the writes. That keeps the partial unique indexes (one PLAYING
    occurrence per session, one occurrence per queue position) satisfied after
    every statement, not just at commit.

    What was surfaced (track, rank, score, algorithm, time, surfaced position,
    exploration mark) is written once by add(); save() changes only the
    lifecycle columns, so a surfaced record can never be rewritten.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, occurrence_id: str) -> Optional[RecommendationOccurrence]:
        record = self._session.get(RecommendationOccurrenceRecord, occurrence_id)
        return _occurrence_from_record(record) if record is not None else None

    def list_for_session(self, session_id: str, status: Optional[OccurrenceStatus] = None) -> List[RecommendationOccurrence]:
        statement = select(RecommendationOccurrenceRecord).where(RecommendationOccurrenceRecord.session_id == session_id)
        if status is not None:
            statement = statement.where(RecommendationOccurrenceRecord.status == OccurrenceStatus(status).value)
        if status is OccurrenceStatus.QUEUED:
            order = (RecommendationOccurrenceRecord.queue_position,)
        else:
            # The order they were surfaced in, which may differ from rank order.
            order = (RecommendationOccurrenceRecord.surfaced_at, RecommendationOccurrenceRecord.surfaced_position, RecommendationOccurrenceRecord.id)
        return [_occurrence_from_record(record) for record in self._session.scalars(statement.order_by(*order))]

    def list_for_listener(self, listener_profile_id: str) -> List[RecommendationOccurrence]:
        statement = (
            select(*_OCCURRENCE_COLUMNS)
            .join(ListeningSessionRecord, ListeningSessionRecord.id == RecommendationOccurrenceRecord.session_id)
            .where(ListeningSessionRecord.listener_profile_id == listener_profile_id)
            .order_by(
                RecommendationOccurrenceRecord.session_id,
                RecommendationOccurrenceRecord.surfaced_at,
                RecommendationOccurrenceRecord.surfaced_position,
                RecommendationOccurrenceRecord.id,
            )
        )
        return [_occurrence_from_record(row) for row in self._session.execute(statement)]

    def add(self, occurrence: RecommendationOccurrence) -> None:
        record = RecommendationOccurrenceRecord(
            id=occurrence.occurrence_id,
            session_id=occurrence.session_id,
            track_id=occurrence.track_id,
            rank=occurrence.rank,
            score=occurrence.score,
            algorithm=occurrence.algorithm,
            surfaced_at=occurrence.surfaced_at,
            surfaced_position=occurrence.surfaced_position,
            is_exploration=occurrence.is_exploration,
        )
        _apply_occurrence(record, occurrence)
        self._session.add(record)
        self._session.flush()

    def save(self, occurrence: RecommendationOccurrence) -> None:
        record = _require_record(
            self._session.get(RecommendationOccurrenceRecord, occurrence.occurrence_id), "occurrence", occurrence.occurrence_id
        )
        _apply_occurrence(record, occurrence)
        self._session.flush()


def _feedback_event_from_record(record: FeedbackEventRecord) -> FeedbackEvent:
    return FeedbackEvent(
        event_id=record.id,
        session_id=record.session_id,
        occurrence_id=record.occurrence_id,
        event_type=record.event_type,
        occurred_at=record.occurred_at,
        played_seconds=record.played_seconds,
        duration_seconds=record.duration_seconds,
    )


class SqlAlchemyFeedbackEventRepository:
    """FeedbackEventRepository port implementation (see ports/sessions.py). Events are raw facts: added, never changed."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_session(self, session_id: str) -> List[FeedbackEvent]:
        statement = (
            select(FeedbackEventRecord)
            .where(FeedbackEventRecord.session_id == session_id)
            .order_by(FeedbackEventRecord.occurred_at, FeedbackEventRecord.id)
        )
        return [_feedback_event_from_record(record) for record in self._session.scalars(statement)]

    def list_for_listener(self, listener_profile_id: str) -> List[FeedbackEvent]:
        statement = (
            select(*_EVENT_COLUMNS)
            .join(ListeningSessionRecord, ListeningSessionRecord.id == FeedbackEventRecord.session_id)
            .where(ListeningSessionRecord.listener_profile_id == listener_profile_id)
            .order_by(FeedbackEventRecord.session_id, FeedbackEventRecord.occurred_at, FeedbackEventRecord.id)
        )
        return [_feedback_event_from_record(row) for row in self._session.execute(statement)]

    def add(self, event: FeedbackEvent) -> None:
        self._session.add(
            FeedbackEventRecord(
                id=event.event_id,
                session_id=event.session_id,
                occurrence_id=event.occurrence_id,
                event_type=event.event_type.value,
                played_seconds=event.played_seconds,
                duration_seconds=event.duration_seconds,
                played_fraction=event.played_fraction,
                occurred_at=event.occurred_at,
            )
        )
        self._session.flush()


def _playlist_from_record(record: PlaylistRecord) -> Playlist:
    return Playlist(
        playlist_id=record.id,
        listener_profile_id=record.listener_profile_id,
        name=record.name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class SqlAlchemyPlaylistRepository:
    """PlaylistRepository port implementation (see ports/playlists.py), over playlists and playlist_items (B7).

    The items of a playlist are replaced as a whole: the old rows are deleted
    first, so the unique positions hold after every statement, even when two
    tracks swap places.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, playlist_id: str) -> Optional[Playlist]:
        record = self._session.get(PlaylistRecord, playlist_id)
        return _playlist_from_record(record) if record is not None else None

    def get_by_name(self, listener_profile_id: str, name: str) -> Optional[Playlist]:
        record = self._session.scalars(
            select(PlaylistRecord).where(PlaylistRecord.listener_profile_id == listener_profile_id, PlaylistRecord.name == name)
        ).first()
        return _playlist_from_record(record) if record is not None else None

    def list_for_listener(self, listener_profile_id: str) -> List[Playlist]:
        statement = (
            select(PlaylistRecord)
            .where(PlaylistRecord.listener_profile_id == listener_profile_id)
            .order_by(PlaylistRecord.created_at, PlaylistRecord.id)
        )
        return [_playlist_from_record(record) for record in self._session.scalars(statement)]

    def track_counts(self, playlist_ids: Iterable[str]) -> Dict[str, int]:
        playlist_ids = list(playlist_ids)
        counts = {playlist_id: 0 for playlist_id in playlist_ids}
        statement = (
            select(PlaylistItemRecord.playlist_id, func.count())
            .where(PlaylistItemRecord.playlist_id.in_(playlist_ids))
            .group_by(PlaylistItemRecord.playlist_id)
        )
        counts.update({playlist_id: count for playlist_id, count in self._session.execute(statement)})
        return counts

    def add(self, playlist: Playlist) -> None:
        self._session.add(
            PlaylistRecord(
                id=playlist.playlist_id,
                listener_profile_id=playlist.listener_profile_id,
                name=playlist.name,
                created_at=playlist.created_at,
                updated_at=playlist.updated_at,
            )
        )
        self._session.flush()

    def save(self, playlist: Playlist) -> None:
        record = _require_record(self._session.get(PlaylistRecord, playlist.playlist_id), "playlist", playlist.playlist_id)
        record.name = playlist.name
        record.updated_at = playlist.updated_at
        self._session.flush()

    def delete(self, playlist_id: str) -> None:
        self._session.execute(delete(PlaylistItemRecord).where(PlaylistItemRecord.playlist_id == playlist_id))
        self._session.execute(delete(PlaylistRecord).where(PlaylistRecord.id == playlist_id))
        self._session.flush()

    def items(self, playlist_id: str) -> List[PlaylistItem]:
        statement = select(PlaylistItemRecord).where(PlaylistItemRecord.playlist_id == playlist_id).order_by(PlaylistItemRecord.position)
        return [
            PlaylistItem(playlist_id=record.playlist_id, track_id=record.track_id, position=record.position, added_at=record.added_at)
            for record in self._session.scalars(statement)
        ]

    def replace_items(self, playlist_id: str, items: Sequence[PlaylistItem]) -> None:
        if any(item.playlist_id != playlist_id for item in items):
            raise ValueError("every item must belong to the playlist")
        self._session.execute(delete(PlaylistItemRecord).where(PlaylistItemRecord.playlist_id == playlist_id))
        self._session.flush()
        for item in items:
            self._session.add(
                PlaylistItemRecord(playlist_id=item.playlist_id, track_id=item.track_id, position=item.position, added_at=item.added_at)
            )
        self._session.flush()



def _labels_json(labels: Sequence[str]) -> str:
    return json.dumps(list(labels), separators=(",", ":"))


def _value_json(dimension: ProfileDimension, value) -> str:
    return json.dumps(list(value) if dimension in CATEGORICAL_DIMENSIONS else value, separators=(",", ":"))


def _value_from_json(dimension: ProfileDimension, text: str):
    value = json.loads(text)
    return tuple(value) if dimension in CATEGORICAL_DIMENSIONS else value


class SqlAlchemyLongTermProfileRepository:
    """LongTermProfileRepository port implementation (see ports/adaptation.py), over the B10 tables.

    Adjustments and their evidence are appended, never updated or deleted.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, listener_profile_id: str) -> Optional[LongTermProfile]:
        record = self._session.get(LongTermProfileRecord, listener_profile_id)
        if record is None:
            return None
        profile = UserProfile(
            preferred_genres=tuple(json.loads(record.preferred_genres_json)),
            preferred_moods=tuple(json.loads(record.preferred_moods_json)),
            preferred_energy=record.preferred_energy,
            preferred_danceability=record.preferred_danceability,
            preferred_tempo_bpm=record.preferred_tempo_bpm,
            preferred_valence=record.preferred_valence,
            preferred_acousticness=record.preferred_acousticness,
        )
        return LongTermProfile(record.listener_profile_id, profile, record.policy_version, record.updated_at)

    def save(self, profile: LongTermProfile) -> None:
        values = profile.profile
        record = self._session.get(LongTermProfileRecord, profile.listener_profile_id)
        if record is None:
            record = LongTermProfileRecord(listener_profile_id=profile.listener_profile_id)
            self._session.add(record)
        record.preferred_genres_json = _labels_json(values.preferred_genres)
        record.preferred_moods_json = _labels_json(values.preferred_moods)
        record.preferred_energy = values.preferred_energy
        record.preferred_danceability = values.preferred_danceability
        record.preferred_tempo_bpm = values.preferred_tempo_bpm
        record.preferred_valence = values.preferred_valence
        record.preferred_acousticness = values.preferred_acousticness
        record.policy_version = profile.policy_version
        record.updated_at = profile.updated_at
        self._session.flush()

    def add_adjustment(self, adjustment: ProfileAdjustment) -> None:
        self._session.add(
            LongTermAdjustmentRecord(
                id=adjustment.adjustment_id,
                listener_profile_id=adjustment.listener_profile_id,
                sequence=adjustment.sequence,
                dimension=adjustment.dimension.value,
                change=adjustment.change.value,
                cause=adjustment.cause.value,
                subject=adjustment.subject,
                previous_json=_value_json(adjustment.dimension, adjustment.previous),
                resulting_json=_value_json(adjustment.dimension, adjustment.resulting),
                reason=adjustment.reason,
                policy_version=adjustment.policy_version,
                created_at=adjustment.created_at,
            )
        )
        self._session.flush()
        for position, reference in enumerate(adjustment.evidence):
            self._session.add(
                LongTermAdjustmentEvidenceRecord(
                    adjustment_id=adjustment.adjustment_id,
                    position=position,
                    session_id=reference.session_id,
                    track_id=reference.track_id,
                    feedback_event_id=reference.feedback_event_id,
                    session_turn_id=reference.session_turn_id,
                    weight=reference.weight,
                )
            )
        self._session.flush()

    def list_adjustments(self, listener_profile_id: str) -> List[ProfileAdjustment]:
        records = list(self._session.scalars(
            select(LongTermAdjustmentRecord)
            .where(LongTermAdjustmentRecord.listener_profile_id == listener_profile_id)
            .order_by(LongTermAdjustmentRecord.sequence)
        ))
        evidence: Dict[str, List[EvidenceReference]] = defaultdict(list)
        if records:
            statement = (
                select(LongTermAdjustmentEvidenceRecord)
                .where(LongTermAdjustmentEvidenceRecord.adjustment_id.in_([record.id for record in records]))
                .order_by(LongTermAdjustmentEvidenceRecord.adjustment_id, LongTermAdjustmentEvidenceRecord.position)
            )
            for row in self._session.scalars(statement):
                evidence[row.adjustment_id].append(
                    EvidenceReference(row.session_id, row.track_id, row.weight, row.feedback_event_id, row.session_turn_id)
                )
        adjustments = []
        for record in records:
            dimension = ProfileDimension(record.dimension)
            adjustments.append(ProfileAdjustment(
                adjustment_id=record.id,
                listener_profile_id=record.listener_profile_id,
                sequence=record.sequence,
                dimension=dimension,
                change=record.change,
                cause=record.cause,
                subject=record.subject,
                previous=_value_from_json(dimension, record.previous_json),
                resulting=_value_from_json(dimension, record.resulting_json),
                reason=record.reason,
                policy_version=record.policy_version,
                created_at=record.created_at,
                evidence=tuple(evidence[record.id]),
            ))
        return adjustments

    def last_sequence(self, listener_profile_id: str) -> int:
        statement = select(func.max(LongTermAdjustmentRecord.sequence)).where(
            LongTermAdjustmentRecord.listener_profile_id == listener_profile_id
        )
        return self._session.scalar(statement) or 0
