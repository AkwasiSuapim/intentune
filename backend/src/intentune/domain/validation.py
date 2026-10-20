"""Validation rules shared by the Prototype 1 domain models (listener, library, and later sessions).

Pure functions with no I/O. models.py keeps its own private helpers; its
public behavior is protected and is not refactored here.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional


def require_canonical_uuid(value: object, field_name: str) -> str:
    """Require a lowercase, hyphenated UUID string, exactly as str(uuid.UUID(...)) renders it."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a UUID") from error
    if str(parsed) != value:
        raise ValueError(f"{field_name} must be a canonical lowercase UUID string")
    return value


def require_utc_datetime(value: object, field_name: str) -> datetime:
    """Require a timezone-aware datetime and normalize it to UTC. Naive datetimes are ambiguous."""
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def optional_utc_datetime(value: object, field_name: str) -> Optional[datetime]:
    return None if value is None else require_utc_datetime(value, field_name)


def require_text(value: object, field_name: str) -> str:
    """Require a string that is not blank; surrounding whitespace is removed."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be blank")
    return cleaned


def optional_text(value: object, field_name: str) -> Optional[str]:
    return None if value is None else require_text(value, field_name)


def require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def new_uuid() -> str:
    """A fresh random UUID4 in canonical form, for new domain identities."""
    return str(uuid.uuid4())
