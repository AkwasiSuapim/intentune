"""Settings for the running backend, read from the process environment (B8).

    DATABASE_URL   SQLite database; unset means backend/data/intentune.db, and a
                   relative path is resolved against backend/ (persistence/db.py)
    MEDIA_ROOT     managed media folder; unset means backend/data/media, and a
                   relative path is resolved against backend/
    CORS_ORIGINS   comma-separated browser origins allowed to call the API;
                   unset means http://localhost:5173 (the Vite dev server)
    API_HOST       where `python -m src.intentune.api` listens; 127.0.0.1
    API_PORT       its port; 8000

backend/.env is not loaded: only the process environment is read. A tool that
loads it (for example `uvicorn --env-file .env`) applies whatever it holds, so
check its DATABASE_URL first.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Tuple

from sqlalchemy.engine import URL

from src.intentune.adapters.managed_media import DEFAULT_MEDIA_ROOT
from src.intentune.persistence.db import BACKEND_ROOT, DATABASE_URL_ENV_VAR, resolve_database_url

DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _media_root(raw: str) -> Path:
    if not raw.strip():
        return DEFAULT_MEDIA_ROOT
    path = Path(raw.strip())
    return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()


def _origins(raw: str) -> Tuple[str, ...]:
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


def _port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError:
        raise ValueError("API_PORT must be a whole number") from None
    if not 1 <= port <= 65535:
        raise ValueError("API_PORT must be from 1 to 65535")
    return port


@dataclass(frozen=True)
class ApiSettings:
    """What the backend needs to start. start_worker and startup_scan exist so tests can keep threads off."""

    database_url: URL
    media_root: Path = DEFAULT_MEDIA_ROOT
    cors_origins: Tuple[str, ...] = DEFAULT_CORS_ORIGINS
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    start_worker: bool = True
    startup_scan: bool = True
    analysis_idle_seconds: float = 30.0

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] = os.environ) -> "ApiSettings":
        origins = environ.get("CORS_ORIGINS")
        return cls(
            database_url=resolve_database_url(environ.get(DATABASE_URL_ENV_VAR)),
            media_root=_media_root(environ.get("MEDIA_ROOT", "")),
            cors_origins=DEFAULT_CORS_ORIGINS if origins is None else _origins(origins),
            host=environ.get("API_HOST", "").strip() or DEFAULT_HOST,
            port=_port(environ.get("API_PORT", "").strip() or str(DEFAULT_PORT)),
        )
