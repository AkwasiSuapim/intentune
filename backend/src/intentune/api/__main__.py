"""Run the backend: `python -m src.intentune.api` from backend/ (B8).

Listens on API_HOST:API_PORT (127.0.0.1:8000 by default). Settings come from
the process environment only; see settings.py.
"""

import logging

import uvicorn

from src.intentune.api.app import create_app
from src.intentune.api.settings import ApiSettings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = ApiSettings.from_environment()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
