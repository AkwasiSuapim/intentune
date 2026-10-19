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

from sqlalchemy import Boolean, DateTime, Index, MetaData, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

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
