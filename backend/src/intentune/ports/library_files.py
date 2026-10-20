"""Library file ports: the listener's source folders, the audio inspector, and managed media.

These are the only ways the library use cases touch files. Paths cross these
ports as plain strings; the application layer never opens a file itself.

Adapters: src/intentune/adapters/local_folders.py,
src/intentune/adapters/mutagen_audio.py, src/intentune/adapters/managed_media.py.
"""

from typing import Iterable, Optional, Protocol

from src.intentune.domain.library import AudioFormat, AudioProbe, DiscoveredFile, EmbeddedTags


class SourceFolders(Protocol):
    def resolve_directory(self, path: str) -> Optional[str]:
        """The absolute, normalized path of an existing directory Intentune may scan, or None.

        Returns None for a missing path, a file, or a folder inside Intentune's own managed media.
        """
        ...

    def list_files(self, root: str) -> Iterable[DiscoveredFile]:
        """Every regular file under root, recursively. Symbolic links and managed media are skipped."""
        ...

    def file_path(self, root: str, relative_path: str) -> str:
        """The absolute path of a file under root. Raises ValueError if it would point outside root."""
        ...

    def sha256(self, path: str) -> str:
        """The SHA-256 of the file's content, as 64 lowercase hex characters. May raise OSError."""
        ...


class AudioInspector(Protocol):
    def probe(self, path: str, audio_format: AudioFormat) -> AudioProbe:
        """Confirm by content that the file is audio_format, and read its stated duration.

        Raises UnsupportedAudioFile if it is not, or OSError if it cannot be read.
        """
        ...

    def read_tags(self, path: str) -> EmbeddedTags:
        """The file's basic embedded tags. Raises TagReadError if they cannot be read."""
        ...


class ManagedMedia(Protocol):
    def store(self, source_path: str, track_id: str, audio_format: AudioFormat, expected_sha256: str) -> int:
        """Copy a file into managed media as <track_id>.<extension> and return its size in bytes.

        The copy appears only once complete, and only if its content hashes to
        expected_sha256; otherwise ManagedCopyMismatch is raised and nothing is
        left behind. May raise OSError.
        """
        ...

    def path(self, track_id: str, audio_format: AudioFormat) -> str:
        """Where a track's managed copy lives. Internal: never shown to the frontend."""
        ...

    def exists(self, track_id: str, audio_format: AudioFormat) -> bool:
        ...

    def discard(self, track_id: str, audio_format: AudioFormat) -> None:
        """Remove a managed copy if it exists."""
        ...
