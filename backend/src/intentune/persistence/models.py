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

from src.intentune.domain.library import AudioFormat, FailureReason, LabelKind, SourceFileStatus, SourceStatus, TrackStatus

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
