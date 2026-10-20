"""ManagedMedia adapter: Intentune's own copies of imported audio (D02, D23).

Managed files live in one flat folder, backend/data/media/ by default
(gitignored), named <track_uuid>.<extension>. The name is built only from a
validated UUID and an allowlisted format, never from the source file name, so
it cannot point outside the folder.

A copy is written to a hidden temporary file while being hashed, flushed to
disk, and moved into place only if its SHA-256 matches the hash taken before
copying. A source file that changes mid-copy therefore never produces a
managed file with unexpected content, and a crash never leaves a half-written
file under a track's name.
"""

import hashlib
import os
from pathlib import Path

from src.intentune.domain.library import AudioFormat, ManagedCopyMismatch
from src.intentune.domain.validation import require_canonical_uuid

DEFAULT_MEDIA_ROOT = Path(__file__).resolve().parents[3] / "data" / "media"
_CHUNK_BYTES = 1024 * 1024


class LocalManagedMedia:
    def __init__(self, root=DEFAULT_MEDIA_ROOT) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def path(self, track_id: str, audio_format: AudioFormat) -> str:
        return str(self._managed_path(track_id, audio_format))

    def store(self, source_path: str, track_id: str, audio_format: AudioFormat, expected_sha256: str) -> int:
        final = self._managed_path(track_id, audio_format)
        self._root.mkdir(parents=True, exist_ok=True)
        partial = final.with_name(f".{final.name}.partial")
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with open(source_path, "rb") as source, open(partial, "wb") as copy:
                for chunk in iter(lambda: source.read(_CHUNK_BYTES), b""):
                    digest.update(chunk)
                    copy.write(chunk)
                    size_bytes += len(chunk)
                copy.flush()
                os.fsync(copy.fileno())
            if digest.hexdigest() != expected_sha256:
                raise ManagedCopyMismatch("The source file changed while it was being imported.")
            os.replace(partial, final)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        return size_bytes

    def exists(self, track_id: str, audio_format: AudioFormat) -> bool:
        return self._managed_path(track_id, audio_format).is_file()

    def discard(self, track_id: str, audio_format: AudioFormat) -> None:
        self._managed_path(track_id, audio_format).unlink(missing_ok=True)

    def _managed_path(self, track_id: str, audio_format: AudioFormat) -> Path:
        require_canonical_uuid(track_id, "track_id")
        path = self._root / f"{track_id}.{AudioFormat(audio_format).extension}"
        if path.parent != self._root:
            raise ValueError("A managed media path must stay inside the media folder.")
        return path
