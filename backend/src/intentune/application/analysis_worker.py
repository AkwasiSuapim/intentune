"""The bounded in-process analysis worker (D28): one background thread, no task queue.

start() recovers jobs a stopped process left behind, then loops:

    process the next pending job
    if none is pending: queue tracks still awaiting analysis
    if still none: sleep until wake() or idle_seconds pass

Exactly one job runs at a time. A job's own failure is recorded on that job
by AnalysisService, so the loop carries on. An error outside a job (for
example a database that is briefly locked) is logged, and the loop retries
after idle_seconds. Nothing ends the thread except stop().

stop() lets the current job finish, then returns. If the process exits
instead, the running job stays RUNNING and is recovered by the next start().

The worker's AnalysisService must have its own UnitOfWork; units of work
are not shared between threads.
"""

import logging
import threading
from typing import Optional

from src.intentune.application.analysis import AnalysisService

logger = logging.getLogger("intentune.analysis")


class AnalysisWorker:
    def __init__(self, service: AnalysisService, idle_seconds: float = 30.0) -> None:
        if idle_seconds <= 0:
            raise ValueError("idle_seconds must be positive")
        self._service = service
        self._idle_seconds = idle_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> None:
        """Start the worker thread. Calling start() on a running worker does nothing."""
        with self._lock:
            if self.is_running:
                return
            self._stop.clear()
            self._wake.clear()
            self._thread = threading.Thread(target=self._run, name="intentune-analysis-worker", daemon=True)
            self._thread.start()

    def wake(self) -> None:
        """Look for work now instead of at the end of the idle wait (for example right after a scan)."""
        self._wake.set()

    def stop(self, timeout: Optional[float] = None) -> bool:
        """Ask the worker to stop after its current job. Returns True once the thread has ended."""
        with self._lock:
            thread = self._thread
            self._stop.set()
            self._wake.set()
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _run(self) -> None:
        try:
            self._service.recover_interrupted()
        except Exception:
            logger.exception("Analysis recovery failed; continuing")
        while not self._stop.is_set():
            try:
                if self._service.process_next() is not None:
                    continue
                if self._service.enqueue_pending():
                    continue
            except Exception:
                logger.exception("Analysis worker error; retrying after %.1f s", self._idle_seconds)
            self._wake.wait(self._idle_seconds)
            self._wake.clear()
