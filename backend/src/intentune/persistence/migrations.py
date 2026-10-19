"""Run Alembic migrations from Python (tests now, application startup later).

From a shell, the same migrations run with `alembic upgrade head` in backend/.
Both paths use backend/alembic.ini and backend/alembic/env.py.
"""

from typing import Union

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from src.intentune.persistence.db import BACKEND_ROOT

ALEMBIC_INI_PATH = BACKEND_ROOT / "alembic.ini"


def alembic_config(database_url: Union[str, URL]) -> Config:
    """An Alembic Config targeting database_url.

    The URL travels in Config.attributes rather than the ini's sqlalchemy.url,
    so a path containing '%' is not mangled by configparser interpolation.
    Logging is left alone so callers keep their own logging configuration.
    """
    config = Config(str(ALEMBIC_INI_PATH))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logging"] = False
    return config


def upgrade_database(database_url: Union[str, URL], revision: str = "head") -> None:
    """Apply migrations to database_url up to revision (default: the latest)."""
    command.upgrade(alembic_config(database_url), revision)
