"""SQLAlchemy ORM records for Prototype 1 persistence.

Records are storage shapes, not domain models. Repositories convert between
the two (see repositories.py), so the domain never imports SQLAlchemy and
these classes never leave the persistence package. Each record class carries
a `Record` suffix to keep it distinct from its domain counterpart.

Schema changes are made with an Alembic migration (backend/alembic/versions/),
never by editing a live database. A test checks that the migrations and the
records below describe the same schema.

Conventions every table follows:

- ids are UUID strings in canonical lowercase hyphenated form (String(36));
- timestamps are UTC (UtcDateTime refuses naive datetimes);
- constraints and indexes get deterministic names from NAMING_CONVENTION,
  which Alembic's SQLite batch mode needs to alter or drop them later.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Type

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from src.intentune.domain.analysis import AnalysisFailureReason, AnalysisJobKind, AnalysisJobStatus, FeatureName
from src.intentune.domain.library import AudioFormat, FailureReason, LabelKind, SourceFileStatus, SourceStatus, TrackStatus
from src.intentune.domain.session import FeedbackEventType, OccurrenceStatus, SessionEndReason, SessionStatus, TurnKind

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UtcDateTime(TypeDecorator):
    """A UTC timestamp column.

    SQLite has no timezone-aware datetime type. This stores the UTC wall-clock
    value and reattaches UTC when reading, so callers always get aware
    datetimes back. Naive datetimes are rejected rather than guessed at.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UtcDateTime requires a timezone-aware datetime")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class ListenerProfileRecord(Base):
    """One row per local listener. Prototype 1 has exactly one, the default (D01).

    The partial unique index allows any number of non-default rows but at most
    one with is_default = 1, so the database itself refuses a second default.
    """

    __tablename__ = "listener_profiles"
    __table_args__ = (
        Index(
            "uq_listener_profiles_is_default",
            "is_default",
            unique=True,
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)


# --- Managed library (B2) ---------------------------------------------------------
#
# Enumerated columns carry a CHECK constraint generated from the domain enum,
# so the database refuses a value the domain does not define. The migration
# spells the same lists out literally.


def _one_of(column: str, enum: Type[Enum], nullable: bool = False) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum)
    clause = f"{column} IN ({values})"
    return f"{column} IS NULL OR {clause}" if nullable else clause


class LibrarySourceRecord(Base):
    """A registered source folder (D03). path is the absolute, normalized folder path."""

    __tablename__ = "library_sources"
    __table_args__ = (CheckConstraint(_one_of("status", SourceStatus), name="status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime, nullable=True)


class TrackRecord(Base):
    """One distinct piece of content in managed media. sha256 is the exact-duplicate key (D24).

    The managed file is <id>.<audio_format> in managed media; no path is stored.
    """

    __tablename__ = "tracks"
    __table_args__ = (
        CheckConstraint(_one_of("audio_format", AudioFormat), name="audio_format"),
        CheckConstraint(_one_of("status", TrackStatus), name="status"),
        CheckConstraint("size_bytes >= 0", name="size_bytes"),
        CheckConstraint("year IS NULL OR year BETWEEN 1 AND 9999", name="year"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="duration_seconds"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_format: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artist: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    album: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    analysis_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)


class TrackLabelRecord(Base):
    """A genre or mood label with provenance (spec §9). At most one primary label per kind per track."""

    __tablename__ = "track_labels"
    __table_args__ = (
        CheckConstraint(_one_of("kind", LabelKind), name="kind"),
        CheckConstraint("is_primary IN (0, 1)", name="is_primary"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence"),
        UniqueConstraint("track_id", "kind", "value", "source", name="uq_track_labels_track_kind_value_source"),
        Index("uq_track_labels_primary", "track_id", "kind", unique=True, sqlite_where=text("is_primary = 1")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("tracks.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False)


class SourceFileRecord(Base):
    """What the last scan recorded about one file in a source: the incremental-scan state (spec §5)."""

    __tablename__ = "source_files"
    __table_args__ = (
        CheckConstraint(_one_of("status", SourceFileStatus), name="status"),
        CheckConstraint(_one_of("failure_reason", FailureReason, nullable=True), name="failure_reason"),
        CheckConstraint("size_bytes >= 0", name="size_bytes"),
        CheckConstraint(
            "status <> 'IMPORTED' OR (track_id IS NOT NULL AND sha256 IS NOT NULL AND failure_reason IS NULL)",
            name="imported_has_track",
        ),
        CheckConstraint("status NOT IN ('UNSUPPORTED', 'FAILED') OR failure_reason IS NOT NULL", name="rejected_has_reason"),
        UniqueConstraint("source_id", "relative_path", name="uq_source_files_source_id_relative_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("library_sources.id"), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    modified_ns: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    track_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("tracks.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)


# --- Background analysis (B3) -----------------------------------------------------


class AnalysisJobRecord(Base):
    """A persisted background job (D28). At most one job per track, kind, and analyzer version."""

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        CheckConstraint(_one_of("kind", AnalysisJobKind), name="kind"),
        CheckConstraint(_one_of("status", AnalysisJobStatus), name="status"),
        CheckConstraint(_one_of("failure_reason", AnalysisFailureReason, nullable=True), name="failure_reason"),
        CheckConstraint("attempts >= 0", name="attempts"),
        CheckConstraint("status <> 'SUCCEEDED' OR failure_reason IS NULL", name="succeeded_has_no_reason"),
        CheckConstraint("status NOT IN ('FAILED', 'SKIPPED') OR failure_reason IS NOT NULL", name="finished_has_reason"),
        UniqueConstraint("track_id", "kind", "analyzer", name="uq_analysis_jobs_track_kind_analyzer"),
        Index("ix_analysis_jobs_status_created_at", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("tracks.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    analyzer: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime, nullable=True)


class TrackFeatureRecord(Base):
    """One measured feature of one track, with provenance (D20). One current value per feature per track."""

    __tablename__ = "track_features"
    __table_args__ = (
        CheckConstraint(_one_of("name", FeatureName), name="name"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence"),
        UniqueConstraint("track_id", "name", name="uq_track_features_track_id_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("tracks.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    analyzer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    analyzer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)


# --- Listening sessions (B4) --------------------------------------------------------
#
# The session row is the current state; turns, occurrences, and feedback
# events are the history (D31). The current track and the queue are the
# session's PLAYING and QUEUED occurrences, so they are rows with constraints,
# not a list stored in the session. The ListeningContext is stored as JSON
# (context_json): it is always read and written whole and never queried by
# field. Composite foreign keys keep a turn's or event's occurrence inside
# the same session.


class ListeningSessionRecord(Base):
    __tablename__ = "listening_sessions"
    __table_args__ = (
        CheckConstraint(_one_of("status", SessionStatus), name="status"),
        CheckConstraint(_one_of("end_reason", SessionEndReason, nullable=True), name="end_reason"),
        CheckConstraint(
            "(status = 'ACTIVE' AND ended_at IS NULL AND end_reason IS NULL) "
            "OR (status = 'ENDED' AND ended_at IS NOT NULL AND end_reason IS NOT NULL)",
            name="end_matches_status",
        ),
        Index(
            "uq_listening_sessions_one_active",
            "listener_profile_id",
            unique=True,
            sqlite_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_listening_sessions_listener_started", "listener_profile_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    listener_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("listener_profiles.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    end_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    context_json: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime, nullable=True)


class RecommendationOccurrenceRecord(Base):
    __tablename__ = "recommendation_occurrences"
    __table_args__ = (
        CheckConstraint(_one_of("status", OccurrenceStatus), name="status"),
        CheckConstraint("rank >= 1", name="rank"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="score"),
        CheckConstraint("queue_position IS NULL OR queue_position >= 0", name="queue_position"),
        CheckConstraint("(status = 'QUEUED') = (queue_position IS NOT NULL)", name="queue_position_while_queued"),
        CheckConstraint("(status IN ('PLAYING', 'PLAYED')) = (started_at IS NOT NULL)", name="started_when_played"),
        CheckConstraint(
            "(status IN ('PLAYED', 'REPLACED', 'DISCARDED')) = (finished_at IS NOT NULL)", name="finished_when_done"
        ),
        UniqueConstraint("id", "session_id", name="uq_recommendation_occurrences_id_session"),
        Index(
            "uq_recommendation_occurrences_one_playing",
            "session_id",
            unique=True,
            sqlite_where=text("status = 'PLAYING'"),
        ),
        Index(
            "uq_recommendation_occurrences_queue_position",
            "session_id",
            "queue_position",
            unique=True,
            sqlite_where=text("queue_position IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("listening_sessions.id"), nullable=False)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("tracks.id"), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    queue_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    surfaced_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UtcDateTime, nullable=True)


class SessionTurnRecord(Base):
    __tablename__ = "session_turns"
    __table_args__ = (
        CheckConstraint(_one_of("kind", TurnKind), name="kind"),
        CheckConstraint("sequence >= 1", name="sequence"),
        CheckConstraint("(kind = 'INITIAL_INTENT') = (sequence = 1)", name="initial_intent_first"),
        CheckConstraint(
            "kind NOT IN ('NOT_FOR_ME', 'MORE_LIKE_THIS') OR occurrence_id IS NOT NULL", name="target_when_required"
        ),
        UniqueConstraint("session_id", "sequence", name="uq_session_turns_session_sequence"),
        ForeignKeyConstraint(
            ["occurrence_id", "session_id"],
            ["recommendation_occurrences.id", "recommendation_occurrences.session_id"],
            name="fk_session_turns_occurrence_same_session",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("listening_sessions.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    context_json: Mapped[str] = mapped_column(Text, nullable=False)
    occurrence_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)


class FeedbackEventRecord(Base):
    """A raw listening fact (spec §9). Interpretation is never stored here."""

    __tablename__ = "feedback_events"
    __table_args__ = (
        CheckConstraint(_one_of("event_type", FeedbackEventType), name="event_type"),
        CheckConstraint("played_seconds IS NULL OR played_seconds >= 0", name="played_seconds"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds > 0", name="duration_seconds"),
        CheckConstraint("played_fraction IS NULL OR played_fraction BETWEEN 0 AND 1", name="played_fraction"),
        CheckConstraint("(played_seconds IS NULL) = (duration_seconds IS NULL)", name="playback_facts_together"),
        CheckConstraint("(played_fraction IS NULL) = (played_seconds IS NULL)", name="fraction_with_facts"),
        CheckConstraint(
            "event_type NOT IN ('SKIP', 'COMPLETE') OR played_seconds IS NOT NULL", name="playback_facts_when_required"
        ),
        ForeignKeyConstraint(
            ["occurrence_id", "session_id"],
            ["recommendation_occurrences.id", "recommendation_occurrences.session_id"],
            name="fk_feedback_events_occurrence_same_session",
        ),
        Index("ix_feedback_events_session_occurred", "session_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("listening_sessions.id"), nullable=False)
    occurrence_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    played_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    played_fraction: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
