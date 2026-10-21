"""LibraryScanCoordinator (B8): scans never overlap, the startup scan runs in the background, and the worker is woken."""

import threading

import pytest

from src.intentune.application.library_scans import LibraryScanCoordinator, ScanInProgress
from src.intentune.domain.library import LibraryError, LibrarySourceNotFound, ScanReport

_SOURCE = "6f1c1c2e-5d36-4c43-8f0e-2f0f1d9e8a11"


class FakeLibrary:
    """A LibraryService stand-in whose scans can be held open, to look at the coordinator mid-scan."""

    def __init__(self, hold=None, error=None):
        self.hold = hold
        self.error = error
        self.scanning = threading.Event()
        self.calls = []

    def scan_source(self, source_id):
        return self._scan(("scan_source", source_id), ScanReport(source_id=source_id, imported=1))

    def rescan_library(self):
        return self._scan(("rescan_library",), [ScanReport(source_id=_SOURCE, imported=2)])

    def _scan(self, call, result):
        self.calls.append(call)
        self.scanning.set()
        if self.hold is not None:
            assert self.hold.wait(timeout=5)
        if self.error is not None:
            raise self.error
        return result


def _coordinator(library, woken=None):
    factory_calls = []

    def factory():
        factory_calls.append(1)
        return library

    on_scanned = (lambda: woken.append(1)) if woken is not None else None
    coordinator = LibraryScanCoordinator(factory, on_scanned) if on_scanned else LibraryScanCoordinator(factory)
    return coordinator, factory_calls


def test_scans_run_in_the_callers_thread_and_return_their_reports():
    woken = []
    library = FakeLibrary()
    coordinator, factory_calls = _coordinator(library, woken)

    assert coordinator.scan_source(_SOURCE) == ScanReport(source_id=_SOURCE, imported=1)
    assert coordinator.rescan_library() == [ScanReport(source_id=_SOURCE, imported=2)]
    assert library.calls == [("scan_source", _SOURCE), ("rescan_library",)]
    assert len(factory_calls) == 2  # a fresh LibraryService (and unit of work) for every scan
    assert woken == [1, 1]
    assert not coordinator.is_scanning


def test_a_scan_is_refused_while_another_runs():
    hold = threading.Event()
    library = FakeLibrary(hold=hold)
    coordinator, _ = _coordinator(library)

    assert coordinator.start_background_rescan() is True
    assert library.scanning.wait(timeout=5)
    assert coordinator.is_scanning
    with pytest.raises(ScanInProgress, match="already running"):
        coordinator.scan_source(_SOURCE)
    with pytest.raises(ScanInProgress):
        coordinator.rescan_library()
    assert coordinator.start_background_rescan() is False

    hold.set()
    assert coordinator.wait(timeout=5)
    assert not coordinator.is_scanning
    assert library.calls == [("rescan_library",)]
    assert issubclass(ScanInProgress, LibraryError)


def test_the_background_rescan_wakes_the_worker_when_it_ends():
    woken = []
    hold = threading.Event()
    coordinator, _ = _coordinator(FakeLibrary(hold=hold), woken)

    coordinator.start_background_rescan()
    assert woken == []
    hold.set()
    assert coordinator.wait(timeout=5)

    assert woken == [1]


def test_a_failed_scan_releases_the_lock_and_still_wakes_the_worker():
    woken = []
    coordinator, _ = _coordinator(FakeLibrary(error=LibrarySourceNotFound(_SOURCE)), woken)

    with pytest.raises(LibrarySourceNotFound):
        coordinator.scan_source(_SOURCE)

    assert not coordinator.is_scanning
    assert woken == [1]


def test_a_failed_background_rescan_is_logged_and_releases_the_lock(caplog):
    coordinator, _ = _coordinator(FakeLibrary(error=RuntimeError("disk gone")))

    assert coordinator.start_background_rescan()
    assert coordinator.wait(timeout=5)

    assert not coordinator.is_scanning
    assert "Library scan failed" in caplog.text
    assert coordinator.start_background_rescan()  # the next scan can start
    assert coordinator.wait(timeout=5)


def test_a_failing_wake_does_not_fail_the_scan(caplog):
    def broken_wake():
        raise RuntimeError("worker gone")

    coordinator = LibraryScanCoordinator(lambda: FakeLibrary(), broken_wake)

    assert coordinator.scan_source(_SOURCE).imported == 1
    assert "After-scan notification failed" in caplog.text


def test_wait_without_a_background_scan_returns_at_once():
    coordinator, _ = _coordinator(FakeLibrary())

    assert coordinator.wait(timeout=0) is True


def test_wait_reports_a_scan_still_running():
    hold = threading.Event()
    coordinator, _ = _coordinator(FakeLibrary(hold=hold))
    coordinator.start_background_rescan()

    assert coordinator.wait(timeout=0.05) is False
    hold.set()
    assert coordinator.wait(timeout=5) is True
