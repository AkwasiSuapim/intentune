"""Library scans, one at a time (Prototype 1, phase B8).

LibraryScanCoordinator runs every scan the running backend starts:

- start_background_rescan(): the startup scan (D25), in its own thread, so
  the API answers while it runs (D26).
- scan_source() / rescan_library(): the manual Import and Rescan Library
  actions. They run in the caller's thread and return the scan reports.

Scans never overlap. Two scans of the same folder would race on the same
files (both would hash, copy, and record a new file), so a scan that would
start while another runs is refused with ScanInProgress, rather than waiting
for it. Each scan gets a fresh LibraryService from library_factory, because
units of work are not shared between threads.

After a scan, on_scanned() is called; the API passes the analysis worker's
wake(), so newly imported tracks are analyzed without waiting for the
worker's idle period.
"""

import logging
import threading
from contextlib import contextmanager
from typing import Callable, Iterator, List, Optional

from src.intentune.application.library import LibraryService
from src.intentune.domain.library import LibraryError, ScanReport

logger = logging.getLogger("intentune.library")


class ScanInProgress(LibraryError):
    """A library scan is already running (API code CONFLICT)."""


def _do_nothing() -> None:
    return None


class LibraryScanCoordinator:
    def __init__(self, library_factory: Callable[[], LibraryService], on_scanned: Callable[[], None] = _do_nothing) -> None:
        self._library_factory = library_factory
        self._on_scanned = on_scanned
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    @property
    def is_scanning(self) -> bool:
        return self._lock.locked()

    def scan_source(self, source_id: str) -> ScanReport:
        with self._exclusive():
            return self._library_factory().scan_source(source_id)

    def rescan_library(self) -> List[ScanReport]:
        with self._exclusive():
            return self._library_factory().rescan_library()

    def start_background_rescan(self) -> bool:
        """Scan every source in a background thread. Returns False, starting nothing, if a scan is running."""
        if not self._lock.acquire(blocking=False):
            return False
        try:
            thread = threading.Thread(target=self._background_rescan, name="intentune-library-scan", daemon=True)
            thread.start()
        except BaseException:
            self._lock.release()
            raise
        self._thread = thread
        return True

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Wait for the background scan, if one was started. Returns True once it has ended."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _background_rescan(self) -> None:
        try:
            reports = self._library_factory().rescan_library()
            logger.info(
                "Library scan finished: %d source(s), %d new track(s)",
                len(reports),
                sum(report.imported for report in reports),
            )
        except Exception:
            logger.exception("Library scan failed")
        finally:
            self._lock.release()
            self._notify()

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        if not self._lock.acquire(blocking=False):
            raise ScanInProgress("A library scan is already running.")
        try:
            yield
        finally:
            self._lock.release()
            self._notify()

    def _notify(self) -> None:
        try:
            self._on_scanned()
        except Exception:
            logger.exception("After-scan notification failed")
