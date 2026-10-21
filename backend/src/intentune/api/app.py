"""The FastAPI application (B8).

create_app() builds an application from settings (by default, the process
environment). Nothing happens at import: the database is migrated and the
background threads start when the application starts serving, in its
lifespan, and stop when it shuts down (container.py lists the steps).

    python -m src.intentune.api                              (from backend/)
    uvicorn --factory src.intentune.api.app:create_app       (the same, via uvicorn)
"""

import random
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from src.intentune.api.container import Container
from src.intentune.api.errors import REQUEST_ID_HEADER, RequestIdMiddleware, install_error_handling
from src.intentune.api.routes import health, library, playlists, sessions, tracks
from src.intentune.api.settings import ApiSettings


def create_app(settings: Optional[ApiSettings] = None, rng_factory: Callable[[], random.Random] = random.Random) -> FastAPI:
    settings = settings if settings is not None else ApiSettings.from_environment()
    container = Container(settings, rng_factory=rng_factory)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            await run_in_threadpool(container.start)
        except BaseException:
            await run_in_threadpool(container.stop)
            raise
        try:
            yield
        finally:
            await run_in_threadpool(container.stop)

    app = FastAPI(
        title="Intentune",
        summary="Local listening sessions over a managed music library (Prototype 1).",
        lifespan=lifespan,
    )
    app.state.container = container
    install_error_handling(app)
    for module in (health, library, tracks, sessions, playlists):
        app.include_router(module.router)

    # The request id middleware sits inside CORS, so its error responses get CORS headers too.
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "HEAD", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Range", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER, "Content-Range", "Accept-Ranges", "Content-Length"],
    )
    return app
