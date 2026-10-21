"""GET and HEAD /api/v1/tracks/{track_id}/audio: a track's audio, by id (spec §25, B8).

Only the track id comes from the client. LibraryService.track_audio() checks
the track and its managed copy, and the file name is built from the validated
id and format (adapters/managed_media.py), so no client input reaches a path.

Starlette's FileResponse serves it. Its range support (verified on the
installed Starlette 1.8.0) is what browsers need to seek: Accept-Ranges:
bytes on every response; 206 Partial Content for a single range (bytes=a-b,
bytes=a-, or a suffix bytes=-n), with the end clamped to the file;
multipart/byteranges for several ranges; 416 with Content-Range: bytes */size
for a range past the end; 400 for a malformed one.
"""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from src.intentune.api.dependencies import ERROR_RESPONSES, ContainerDep
from src.intentune.domain.library import AudioFormat

router = APIRouter(prefix="/api/v1/tracks", tags=["tracks"], responses=ERROR_RESPONSES)

MEDIA_TYPES = {
    AudioFormat.MP3: "audio/mpeg",
    AudioFormat.M4A: "audio/mp4",
    AudioFormat.FLAC: "audio/flac",
    AudioFormat.OGG: "audio/ogg",
    AudioFormat.OPUS: "audio/ogg",
    AudioFormat.WAV: "audio/wav",
}


@router.api_route("/{track_id}/audio", methods=["GET", "HEAD"], response_class=FileResponse)
def track_audio(track_id: str, container: ContainerDep) -> FileResponse:
    audio = container.library().track_audio(track_id)
    return FileResponse(audio.path, media_type=MEDIA_TYPES[audio.track.audio_format])
