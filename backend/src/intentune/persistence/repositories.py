"""SQLAlchemy repositories: implement the storage ports over ORM records.

A repository works inside a Session it is given and never commits; the unit
of work that created it owns the transaction (see unit_of_work.py). It
accepts and returns domain models only, so ORM records stay inside the
persistence package.
"""

import dataclasses
import json
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from src.intentune.domain.analysis import AnalysisJob, AnalysisJobKind, AnalysisJobStatus, TrackFeature
from src.intentune.domain.models import ListeningContext
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
from src.intentune.domain.validation import new_uuid
from src.intentune.persistence.models import (
    AnalysisJobRecord,
    FeedbackEventRecord,
    LibrarySourceRecord,
    ListenerProfileRecord,
    ListeningSessionRecord,
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
        score=record.score,
        queue_position=record.queue_position,
        started_at=record.started_at,
        finished_at=record.finished_at,
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
            order = (RecommendationOccurrenceRecord.surfaced_at, RecommendationOccurrenceRecord.rank, RecommendationOccurrenceRecord.id)
        return [_occurrence_from_record(record) for record in self._session.scalars(statement.order_by(*order))]

    def add(self, occurrence: RecommendationOccurrence) -> None:
        record = RecommendationOccurrenceRecord(
            id=occurrence.occurrence_id,
            session_id=occurrence.session_id,
            track_id=occurrence.track_id,
            rank=occurrence.rank,
            score=occurrence.score,
            algorithm=occurrence.algorithm,
            surfaced_at=occurrence.surfaced_at,
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
