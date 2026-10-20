"""AnalysisWorker: one real background thread over a real SQLite database.

Each test waits on observable state with a deadline instead of sleeping for
a fixed time. The worker gets its own unit of work, as it must in the app.
"""

import logging
import threading
import time
from datetime import datetime, timezone

import pytest

from src.intentune.adapters.managed_media import LocalManagedMedia
from src.intentune.application.analysis import AnalysisService
from src.intentune.application.analysis_worker import AnalysisWorker
from src.intentune.domain.analysis import AnalysisFailureReason, AnalysisJobStatus, AnalysisResult, AnalyzerIdentity, FeatureName
from src.intentune.domain.library import TrackStatus
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork

_DEADLINE_SECONDS = 15


class ControlledAnalyzer:
    """A fake analyzer the test can make fail for one track, or hold mid-analysis."""

    def __init__(self):
        self.identity = AnalyzerIdentity(name="test.worker", version="1")
        self.fail_track_ids = set()
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.threads = set()

    def supports(self, audio_format):
        return True

    def analyze(self, path, audio_format):
        self.threads.add(threading.current_thread().name)
        self.started.set()
        self.release.wait(_DEADLINE_SECONDS)
        if any(track_id in path for track_id in self.fail_track_ids):
            raise RuntimeError("analyzer bug")
        return AnalysisResult(values={FeatureName.RMS_LEVEL: 0.1})


def _wait_until(condition, deadline=_DEADLINE_SECONDS):
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def analyzer():
    return ControlledAnalyzer()


@pytest.fixture
def service(session_factory, analyzer, media_root):
    return AnalysisService(SqlAlchemyUnitOfWork(session_factory), analyzer, LocalManagedMedia(media_root))


@pytest.fixture
def observer(session_factory, analyzer, media_root):
    """A second service on the test thread, for reading state the worker writes."""
    return AnalysisService(SqlAlchemyUnitOfWork(session_factory), analyzer, LocalManagedMedia(media_root))


@pytest.fixture
def worker(service):
    worker = AnalysisWorker(service, idle_seconds=0.05)
    yield worker
    worker.stop(timeout=_DEADLINE_SECONDS)


def _import(library, audio, folder, count):
    for seed in range(1, count + 1):
        audio.mp3(folder / f"song{seed}.mp3", seed=seed)
    source = library.register_source(str(folder))
    library.scan_source(source.source_id)
    return source


def _all_ready(library):
    tracks = library.list_tracks()
    return bool(tracks) and all(track.status is TrackStatus.READY for track in tracks)


def _finished_count(observer):
    return sum(job.status not in (AnalysisJobStatus.PENDING, AnalysisJobStatus.RUNNING) for job in observer.list_jobs())


def test_the_worker_queues_and_analyzes_every_track_then_stops(worker, library, audio, tmp_path, analyzer):
    _import(library, audio, tmp_path / "music", 3)

    worker.start()

    assert _wait_until(lambda: _all_ready(library))
    assert worker.stop(timeout=_DEADLINE_SECONDS)
    assert not worker.is_running
    assert analyzer.threads == {"intentune-analysis-worker"}


def test_wake_picks_up_tracks_imported_while_idle(session_factory, analyzer, media_root, library, audio, tmp_path):
    service = AnalysisService(SqlAlchemyUnitOfWork(session_factory), analyzer, LocalManagedMedia(media_root))
    worker = AnalysisWorker(service, idle_seconds=60)
    try:
        worker.start()
        time.sleep(0.2)  # the worker finds nothing and settles into its 60-second idle wait
        _import(library, audio, tmp_path / "music", 1)

        worker.wake()

        assert _wait_until(lambda: _all_ready(library), deadline=10)
    finally:
        assert worker.stop(timeout=_DEADLINE_SECONDS)


def test_a_failing_job_does_not_stop_the_worker(worker, library, audio, tmp_path, analyzer, observer):
    _import(library, audio, tmp_path / "music", 3)
    broken = library.list_tracks()[1].track_id
    analyzer.fail_track_ids.add(broken)

    worker.start()

    assert _wait_until(lambda: _finished_count(observer) == 3)
    jobs = {job.track_id: job for job in observer.list_jobs()}
    assert jobs[broken].failure_reason is AnalysisFailureReason.ANALYZER_ERROR
    assert sum(job.status is AnalysisJobStatus.SUCCEEDED for job in jobs.values()) == 2
    assert worker.is_running


def test_errors_outside_a_job_are_logged_and_the_worker_carries_on(session_factory, analyzer, media_root, library, audio, tmp_path, caplog):
    class FlakyService(AnalysisService):
        failures = 1

        def process_next(self):
            if self.failures:
                self.failures -= 1
                raise RuntimeError("database is locked")
            return super().process_next()

    service = FlakyService(SqlAlchemyUnitOfWork(session_factory), analyzer, LocalManagedMedia(media_root))
    worker = AnalysisWorker(service, idle_seconds=0.05)
    _import(library, audio, tmp_path / "music", 1)

    with caplog.at_level(logging.ERROR, logger="intentune.analysis"):
        worker.start()
        try:
            assert _wait_until(lambda: _all_ready(library))
        finally:
            assert worker.stop(timeout=_DEADLINE_SECONDS)

    assert any("Analysis worker error" in record.getMessage() for record in caplog.records)


def test_start_recovers_jobs_a_stopped_process_left_running(worker, library, audio, tmp_path, observer, session_factory):
    _import(library, audio, tmp_path / "music", 1)
    observer.enqueue_pending()
    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:  # a crash right after claiming
        unit_of_work.analysis_jobs.claim_next(datetime.now(timezone.utc))
        unit_of_work.commit()

    worker.start()

    assert _wait_until(lambda: _all_ready(library))
    [job] = observer.list_jobs()
    assert (job.status, job.attempts) == (AnalysisJobStatus.SUCCEEDED, 2)


def test_stop_lets_the_current_job_finish(worker, library, audio, tmp_path, analyzer, observer):
    _import(library, audio, tmp_path / "music", 1)
    analyzer.release.clear()
    worker.start()
    assert analyzer.started.wait(_DEADLINE_SECONDS)

    assert worker.stop(timeout=0.2) is False
    assert worker.is_running
    analyzer.release.set()

    assert worker.stop(timeout=_DEADLINE_SECONDS) is True
    [job] = observer.list_jobs()
    assert job.status is AnalysisJobStatus.SUCCEEDED


def test_start_twice_runs_one_thread_and_the_worker_can_restart(worker):
    worker.start()
    worker.start()

    assert [thread.name for thread in threading.enumerate()].count("intentune-analysis-worker") == 1
    assert worker.stop(timeout=_DEADLINE_SECONDS)
    worker.start()
    assert worker.is_running


def test_stop_before_start_is_harmless(service):
    assert AnalysisWorker(service).stop() is True


@pytest.mark.parametrize("idle_seconds", [0, -1])
def test_idle_seconds_must_be_positive(service, idle_seconds):
    with pytest.raises(ValueError):
        AnalysisWorker(service, idle_seconds=idle_seconds)
