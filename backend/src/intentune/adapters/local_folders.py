"""SourceFolders adapter: the listener's music folders on the local filesystem.

Scanning is conservative:

- only regular files are reported; symbolic links (files or folders) are
  skipped, so a link cannot pull files from outside the registered folder;
- a folder is entered only if its resolved location is still inside the
  source, which also covers Windows junctions (Python 3.11 does not report
  them as links);
- each directory is visited at most once (tracked by device and inode), so a
  junction or link loop cannot make a scan run forever;
- excluded directories, normally Intentune's own managed media, are never
  entered, and cannot be registered as sources;
- relative paths are re-checked against the root before use.

Files are listed in a stable, sorted order.
"""

import hashlib
import os
import stat
from pathlib import Path
from typing import Iterable, Iterator, Optional, Set, Tuple

from src.intentune.domain.library import DiscoveredFile, require_relative_path

_CHUNK_BYTES = 1024 * 1024


class LocalSourceFolders:
    def __init__(self, excluded_directories: Iterable = ()) -> None:
        self._excluded = tuple(Path(directory).resolve() for directory in excluded_directories)

    def resolve_directory(self, path: str) -> Optional[str]:
        try:
            resolved = Path(path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        if not resolved.is_dir() or self._is_excluded(resolved):
            return None
        return str(resolved)

    def list_files(self, root: str) -> Iterator[DiscoveredFile]:
        root_path = Path(root)
        resolved_root = root_path.resolve()
        visited: Set[Tuple[int, int]] = set()
        for directory, subdirectories, filenames in os.walk(root_path, followlinks=False):
            current = Path(directory)
            identity = _identity(current)
            if identity is None or identity in visited:
                subdirectories[:] = []
                continue
            visited.add(identity)
            subdirectories[:] = sorted(
                name for name in subdirectories if self._may_enter(current / name, resolved_root)
            )
            for name in sorted(filenames):
                path = current / name
                try:
                    details = path.lstat()
                except OSError:
                    continue
                if not stat.S_ISREG(details.st_mode):
                    continue
                yield DiscoveredFile(
                    relative_path=path.relative_to(root_path).as_posix(),
                    size_bytes=details.st_size,
                    modified_ns=details.st_mtime_ns,
                )

    def file_path(self, root: str, relative_path: str) -> str:
        require_relative_path(relative_path)
        root_path = Path(root).resolve()
        candidate = (root_path / relative_path).resolve()
        if candidate != root_path and root_path not in candidate.parents:
            raise ValueError("The file path points outside its source folder.")
        return str(candidate)

    def sha256(self, path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _is_excluded(self, path: Path) -> bool:
        return any(path == excluded or excluded in path.parents for excluded in self._excluded)

    def _may_enter(self, path: Path, resolved_root: Path) -> bool:
        if path.is_symlink():
            return False
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError):
            return False
        return resolved_root in resolved.parents and not self._is_excluded(resolved)


def _identity(path: Path) -> Optional[Tuple[int, int]]:
    try:
        details = path.stat()
    except OSError:
        return None
    return (details.st_dev, details.st_ino)
