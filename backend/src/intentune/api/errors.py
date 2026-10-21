"""The error envelope and request IDs (spec §26, B8).

Every error the API answers has one shape:

    {"error": {"code": "TRACK_NOT_FOUND", "message": "The track does not exist.",
               "details": {}, "request_id": "..."}}

and every response carries the same id in its X-Request-ID header. A client
may send its own X-Request-ID (1 to 64 letters, digits, '.', '_', or '-');
anything else is replaced by a generated id.

Messages are written for the listener. They never include a stack trace or a
filesystem path: errors that name resources get fixed messages, and the
messages passed through (session transitions, validation) are the
application's own, which name no paths. An unexpected error is logged with
its request id and answered with a generic INTERNAL_ERROR.

Two kinds of response come from the framework instead: a Range header the
audio route cannot parse (400) or satisfy (416) gets Starlette's plain-text
reply, which media elements handle on their own.
"""

import logging
import re
import uuid
from typing import Any, Dict, Optional, Tuple, Type

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.intentune.application.library_scans import ScanInProgress
from src.intentune.domain.library import InvalidLibrarySource, LibrarySourceNotFound, TrackNotFound, TrackUnavailable
from src.intentune.domain.playlist import (
    InvalidPlaylistOrder,
    PlaylistNameTaken,
    PlaylistNotFound,
    TrackAlreadyInPlaylist,
    TrackNotInPlaylist,
)
from src.intentune.domain.session import InvalidSessionTransition, RecommendationOccurrenceNotFound, SessionNotFound

logger = logging.getLogger("intentune.api")

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Domain and application errors: (status, code, message). A message of None passes the error's own text through.
_ERRORS: Dict[Type[Exception], Tuple[int, str, Optional[str]]] = {
    SessionNotFound: (404, "SESSION_NOT_FOUND", "The session does not exist."),
    RecommendationOccurrenceNotFound: (404, "RECOMMENDATION_NOT_FOUND", "The recommendation does not exist in this session."),
    InvalidSessionTransition: (409, "INVALID_SESSION_TRANSITION", None),
    TrackNotFound: (404, "TRACK_NOT_FOUND", "The track does not exist."),
    TrackUnavailable: (409, "TRACK_UNAVAILABLE", "The track's audio file is missing. Rescan the library to restore it."),
    LibrarySourceNotFound: (404, "SOURCE_NOT_FOUND", "The library source does not exist."),
    InvalidLibrarySource: (422, "VALIDATION_ERROR", "The path is not an existing folder Intentune can scan."),
    ScanInProgress: (409, "CONFLICT", "A library scan is already running. Try again when it has finished."),
    PlaylistNotFound: (404, "PLAYLIST_NOT_FOUND", "The playlist does not exist."),
    PlaylistNameTaken: (409, "CONFLICT", "You already have a playlist with this name."),
    TrackAlreadyInPlaylist: (409, "CONFLICT", "The track is already in this playlist."),
    TrackNotInPlaylist: (404, "TRACK_NOT_FOUND", "The track is not in this playlist."),
    InvalidPlaylistOrder: (422, "VALIDATION_ERROR", None),
    # The domain's and application's own checks on values that passed the request schema.
    ValueError: (422, "VALIDATION_ERROR", None),
}

_HTTP_CODES = {404: ("NOT_FOUND", "There is nothing here."), 405: ("METHOD_NOT_ALLOWED", "This method is not allowed here.")}


def error_response(
    request_id: str,
    status_code: int,
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details or {}, "request_id": request_id}}
    return JSONResponse(body, status_code=status_code, headers=headers)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def _incoming_request_id(scope: Scope) -> str:
    for name, value in scope.get("headers", ()):
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            if _REQUEST_ID.match(candidate):
                return candidate
            break
    return uuid.uuid4().hex


class RequestIdMiddleware:
    """Gives every request an id, puts it on the response, and turns an unexpected error into INTERNAL_ERROR.

    Pure ASGI, so it does not buffer streamed responses such as audio. An error
    after the response has started cannot be answered any more; it is logged
    and re-raised, and the server closes the connection.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        started = False

        async def send_with_id(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            logger.exception("Unexpected error (request %s)", request_id)
            if started:
                raise
            response = error_response(request_id, 500, "INTERNAL_ERROR", "Something went wrong. Please try again.")
            await response(scope, receive, send_with_id)


async def _domain_error(request: Request, error: Exception) -> JSONResponse:
    status_code, code, message = next(
        _ERRORS[cls] for cls in type(error).__mro__ if cls in _ERRORS
    )
    return error_response(_request_id(request), status_code, code, message if message is not None else str(error))


async def _response_model_error(request: Request, error: Exception) -> JSONResponse:
    """A Pydantic error outside request parsing is the server's fault, not the client's."""
    request_id = _request_id(request)
    logger.error("Response could not be built (request %s): %s", request_id, type(error).__name__)
    return error_response(request_id, 500, "INTERNAL_ERROR", "Something went wrong. Please try again.")


async def _request_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    problems = [
        {"location": list(problem.get("loc", ())), "message": problem.get("msg", ""), "type": problem.get("type", "")}
        for problem in error.errors()
    ]
    if any(problem["type"] == "json_invalid" for problem in problems):
        return error_response(_request_id(request), 400, "VALIDATION_ERROR", "The request body is not valid JSON.", {"errors": problems})
    return error_response(_request_id(request), 422, "VALIDATION_ERROR", "The request is not valid.", {"errors": problems})


async def _http_error(request: Request, error: HTTPException) -> JSONResponse:
    code, message = _HTTP_CODES.get(error.status_code, ("VALIDATION_ERROR", "The request is not valid."))
    if error.status_code >= 500:
        code, message = "INTERNAL_ERROR", "Something went wrong. Please try again."
    return error_response(_request_id(request), error.status_code, code, message, headers=dict(error.headers or {}))


def install_error_handling(app: FastAPI) -> None:
    for error_type in _ERRORS:
        app.add_exception_handler(error_type, _domain_error)
    app.add_exception_handler(ValidationError, _response_model_error)
    app.add_exception_handler(RequestValidationError, _request_validation_error)
    app.add_exception_handler(HTTPException, _http_error)
