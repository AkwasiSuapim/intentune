"""AnalysisService against a migrated database, real managed media, and the B2 library.

Covers the behaviors the execution guide requires for B3 (§6): tracks stay
usable during analysis, a failing track does not stop the others,
interrupted jobs recover, and reanalysis follows an analyzer version change.
It also covers idempotent queuing, retries, skips, and missing managed
copies. A fake analyzer controls each outcome; one test runs the real
SignalLevelAnalyzer end to end.
"""

import math
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.intentune.adapters.managed_media import LocalManagedMedia
from src.intentune.adapters.signal_levels import SignalLevelAnalyzer
from src.intentune.application.analysis import AnalysisPolicy, AnalysisService
from src.intentune.domain.analysis import (
    AnalysisFailureReason,
    AnalysisJobStatus,
    AnalysisResult,
    AnalyzerIdentity,
    AudioDecodeError,
    FeatureName,
)
from src.intentune.domain.library import TrackStatus
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork


class FakeAnalyzer:
    def __init__(self, version="1", supported=True):
        self._identity = AnalyzerIdentity(name="test.fake", version=version)
        self.supported = supported
        self.calls = []
        self.failures = {}
        self.during = None
        self.values = {FeatureName.SAMPLE_PEAK: 0.5, FeatureName.RMS_LEVEL: 0.25, FeatureName.DECODED_DURATION_SECONDS: 1.0}

    @property
    def identity(self):
        return self._identity

    def supports(self, audio_format):
        return self.supported

    def analyze(self, path, audio_format):
        track_id = Path(path).stem
        self.calls.append(track_id)
        if self.during is not None:
            self.during(track_id)
        pending_failures = self.failures.get(track_id)
        if pending_failures:
            raise pending_failures.pop(0)
        return AnalysisResult(values=dict(self.values))


@pytest.fixture
def media(media_root):
    return LocalManagedMedia(media_root)


@pytest.fixture
def fake():
    return FakeAnalyzer()


@pytest.fixture
def analysis_unit_of_work(session_factory):
    """The analysis side gets its own unit of work, as the worker thread does."""
    return SqlAlchemyUnitOfWork(session_factory)


@pytest.fixture
def analysis(analysis_unit_of_work, fake, media):
    return AnalysisService(analysis_unit_of_work, fake, media)


@pytest.fixture
def music(tmp_path):
    return tmp_path / "music"


def _import(library, audio, music, *names):
    for seed, name in enumerate(names, start=1):
        audio.mp3(music / name, seed=seed)
    source = library.register_source(str(music))
    library.scan_source(source.source_id)
    return source, {track.original_filename: track for track in library.list_tracks()}


def _jobs_by_track(analysis):
    return {job.track_id: job for job in analysis.list_jobs()}


# --- Queue ---------------------------------------------------------------------


def test_enqueue_queues_each_track_awaiting_analysis_once(library, analysis, audio, music):
    _, tracks = _import(library, audio, music, "a.mp3", "b.mp3")

    assert analysis.enqueue_pending() == 2
    assert analysis.enqueue_pending() == 0
    jobs = analysis.list_jobs()
    assert sorted(job.track_id for job in jobs) == sorted(track.track_id for track in tracks.values())
    assert all(job.status is AnalysisJobStatus.PENDING and job.analyzer == "test.fake@1" for job in jobs)


def test_enqueue_skips_tracks_without_a_managed_copy_and_tracks_already_analyzed(library, analysis, audio, music):
    _, tracks = _import(library, audio, music, "a.mp3", "b.mp3")
    library.mark_track_unavailable(tracks["a.mp3"].track_id)

    assert analysis.enqueue_pending() == 1
    analysis.run_until_idle()

    assert analysis.enqueue_pending() == 0
    assert set(_jobs_by_track(analysis)) == {tracks["b.mp3"].track_id}


# --- Processing ----------------------------------------------------------------------


def test_analysis_records_features_with_provenance_and_marks_the_track_ready(library, analysis, audio, music):
    _, tracks = _import(library, audio, music, "a.mp3")
    track = tracks["a.mp3"]
    analysis.enqueue_pending()

    finished = analysis.process_next()

    assert (finished.status, finished.attempts, finished.failure_reason) == (AnalysisJobStatus.SUCCEEDED, 1, None)
    ready = library.get_track(track.track_id)
    assert (ready.status, ready.analysis_version) == (TrackStatus.READY, "test.fake@1")
    features = {feature.name: feature for feature in analysis.features_for(track.track_id)}
    assert {name: feature.value for name, feature in features.items()} == {
        FeatureName.SAMPLE_PEAK: 0.5,
        FeatureName.RMS_LEVEL: 0.25,
        FeatureName.DECODED_DURATION_SECONDS: 1.0,
    }
    assert all((feature.analyzer_name, feature.analyzer_version, feature.confidence) == ("test.fake", "1", None) for feature in features.values())
    assert analysis.process_next() is None


def test_tracks_stay_usable_and_the_library_stays_writable_while_analysis_runs(library, analysis, fake, audio, music):
    source, tracks = _import(library, audio, music, "a.mp3")
    track_id = tracks["a.mp3"].track_id
    seen = {}

    def during(analyzed_id):
        seen["status"] = library.get_track(analyzed_id).status
        seen["listed"] = [track.track_id for track in library.list_tracks()]
        seen["rescan"] = library.scan_source(source.source_id)  # a write: no analysis transaction is held open

    fake.during = during
    analysis.enqueue_pending()
    analysis.process_next()

    assert seen["status"] is TrackStatus.ANALYZING
    assert seen["listed"] == [track_id]
    assert seen["rescan"].unchanged == 1
    assert library.get_track(track_id).status is TrackStatus.READY


def test_a_failing_track_does_not_stop_the_others(library, analysis, fake, audio, music):
    _, tracks = _import(library, audio, music, "a.mp3", "b.mp3", "c.mp3")
    broken = tracks["b.mp3"].track_id
    fake.failures[broken] = [ZeroDivisionError("analyzer bug")]
    analysis.enqueue_pending()

    assert analysis.run_until_idle() == 3

    jobs = _jobs_by_track(analysis)
    assert (jobs[broken].status, jobs[broken].failure_reason) == (AnalysisJobStatus.FAILED, AnalysisFailureReason.ANALYZER_ERROR)
    assert jobs[broken].error_message == "Unexpected ZeroDivisionError."
    assert library.get_track(broken).status is TrackStatus.IMPORTED
    others = [tracks[name].track_id for name in ("a.mp3", "c.mp3")]
    assert all(library.get_track(track_id).status is TrackStatus.READY for track_id in others)
    assert analysis.enqueue_pending() == 0


def test_decode_errors_fail_without_retrying(library, analysis, fake, audio, music):
    _, tracks = _import(library, audio, music, "a.mp3")
    track_id = tracks["a.mp3"].track_id
    fake.failures[track_id] = [AudioDecodeError("The audio could not be decoded: Format not recognised.")]
    analysis.enqueue_pending()

    job = analysis.process_next()

    assert (job.status, job.failure_reason, job.attempts) == (AnalysisJobStatus.FAILED, AnalysisFailureReason.DECODE_ERROR, 1)
    assert analysis.process_next() is None
    assert analysis.enqueue_pending() == 0
    assert library.get_track(track_id).status is TrackStatus.IMPORTED


def test_read_errors_are_retried_until_attempts_run_out(library, analysis_unit_of_work, fake, media, audio, music):
    analysis = AnalysisService(analysis_unit_of_work, fake, media, policy=AnalysisPolicy(max_attempts=2))
    _, tracks = _import(library, audio, music, "a.mp3")
    track_id = tracks["a.mp3"].track_id
    fake.failures[track_id] = [PermissionError(13, "Permission denied", "C:/private/music.mp3")] * 2
    analysis.enqueue_pending()

    first = analysis.process_next()
    second = analysis.process_next()

    assert (first.status, first.failure_reason, first.attempts) == (AnalysisJobStatus.PENDING, AnalysisFailureReason.IO_ERROR, 1)
    assert (second.status, second.failure_reason, second.attempts) == (AnalysisJobStatus.FAILED, AnalysisFailureReason.IO_ERROR, 2)
    assert "private" not in second.error_message
    assert second.error_message == "The managed copy could not be read (Permission denied)."
    assert library.get_track(track_id).status is TrackStatus.IMPORTED


def test_a_read_error_that_clears_succeeds_on_retry(library, analysis, fake, audio, music):
    _, tracks = _import(library, audio, music, "a.mp3")
    track_id = tracks["a.mp3"].track_id
    fake.failures[track_id] = [OSError(5, "Input/output error")]
    analysis.enqueue_pending()

    assert analysis.run_until_idle() == 2

    [job] = analysis.list_jobs()
    assert (job.status, job.attempts) == (AnalysisJobStatus.SUCCEEDED, 2)
    assert library.get_track(track_id).status is TrackStatus.READY


def test_formats_the_analyzer_cannot_decode_are_skipped(library, analysis, fake, audio, music):
    _, tracks = _import(library, audio, music, "a.mp3")
    track_id = tracks["a.mp3"].track_id
    fake.supported = False
    analysis.enqueue_pending()

    job = analysis.process_next()

    assert (job.status, job.failure_reason) == (AnalysisJobStatus.SKIPPED, AnalysisFailureReason.FORMAT_NOT_SUPPORTED)
    assert fake.calls == []
    assert library.get_track(track_id).status is TrackStatus.IMPORTED
    assert analysis.enqueue_pending() == 0


def test_a_missing_managed_copy_marks_the_track_unavailable_and_requeues_after_repair(library, analysis, audio, music, media_root):
    source, tracks = _import(library, audio, music, "a.mp3")
    track = tracks["a.mp3"]
    analysis.enqueue_pending()
    (media_root / f"{track.track_id}.mp3").unlink()

    job = analysis.process_next()

    assert (job.status, job.failure_reason) == (AnalysisJobStatus.FAILED, AnalysisFailureReason.MISSING_MANAGED_FILE)
    assert library.get_track(track.track_id).status is TrackStatus.MISSING_MANAGED_FILE
    assert analysis.enqueue_pending() == 0

    assert library.scan_source(source.source_id).repaired == 1
    assert analysis.enqueue_pending() == 1
    assert analysis.process_next().status is AnalysisJobStatus.SUCCEEDED
    assert library.get_track(track.track_id).status is TrackStatus.READY


def test_a_repaired_analyzed_track_returns_to_ready(library, analysis, audio, music, media_root):
    source, tracks = _import(library, audio, music, "a.mp3")
    track_id = tracks["a.mp3"].track_id
    analysis.enqueue_pending()
    analysis.run_until_idle()
    library.mark_track_unavailable(track_id)
    (media_root / f"{track_id}.mp3").unlink()

    assert library.scan_source(source.source_id).repaired == 1

    assert library.get_track(track_id).status is TrackStatus.READY
    assert analysis.enqueue_pending() == 0


# --- Recovery ----------------------------------------------------------------------


def _interrupt(analysis_unit_of_work, library):
    """What a crash leaves: a job claimed (RUNNING) and its track ANALYZING, with nothing finishing it."""
    with analysis_unit_of_work:
        job = analysis_unit_of_work.analysis_jobs.claim_next(datetime.now(timezone.utc))
        track = analysis_unit_of_work.tracks.get(job.track_id)
        analysis_unit_of_work.tracks.save(track.with_status(TrackStatus.ANALYZING, datetime.now(timezone.utc)))
        analysis_unit_of_work.commit()
    return job


def test_interrupted_jobs_are_recovered_and_completed(library, analysis, analysis_unit_of_work, audio, music):
    _, tracks = _import(library, audio, music, "a.mp3")
    track_id = tracks["a.mp3"].track_id
    analysis.enqueue_pending()
    _interrupt(analysis_unit_of_work, library)
    assert library.get_track(track_id).status is TrackStatus.ANALYZING

    assert analysis.recover_interrupted() == 1

    [job] = analysis.list_jobs()
    assert (job.status, job.attempts, job.failure_reason) == (AnalysisJobStatus.PENDING, 1, AnalysisFailureReason.INTERRUPTED)
    assert library.get_track(track_id).status is TrackStatus.IMPORTED
    finished = analysis.process_next()
    assert (finished.status, finished.attempts) == (AnalysisJobStatus.SUCCEEDED, 2)
    assert library.get_track(track_id).status is TrackStatus.READY


def test_a_job_interrupted_on_every_attempt_fails(library, analysis_unit_of_work, fake, media, audio, music):
    analysis = AnalysisService(analysis_unit_of_work, fake, media, policy=AnalysisPolicy(max_attempts=2))
    _, tracks = _import(library, audio, music, "a.mp3")
    analysis.enqueue_pending()

    for _ in range(2):
        _interrupt(analysis_unit_of_work, library)
        analysis.recover_interrupted()

    [job] = analysis.list_jobs()
    assert (job.status, job.failure_reason, job.attempts) == (AnalysisJobStatus.FAILED, AnalysisFailureReason.INTERRUPTED, 2)
    assert analysis.process_next() is None
    assert library.get_track(tracks["a.mp3"].track_id).status is TrackStatus.IMPORTED


def test_recovery_with_nothing_interrupted_changes_nothing(library, analysis, audio, music):
    _import(library, audio, music, "a.mp3")
    analysis.enqueue_pending()

    assert analysis.recover_interrupted() == 0
    assert [job.status for job in analysis.list_jobs()] == [AnalysisJobStatus.PENDING]


# --- Analyzer versions ---------------------------------------------------------------


def test_a_new_analyzer_version_reanalyzes_while_the_track_stays_ready(library, analysis, analysis_unit_of_work, media, audio, music):
    _, tracks = _import(library, audio, music, "a.mp3")
    track_id = tracks["a.mp3"].track_id
    analysis.enqueue_pending()
    analysis.run_until_idle()
    upgraded = FakeAnalyzer(version="2")
    upgraded.values = {FeatureName.SAMPLE_PEAK: 0.75, FeatureName.RMS_LEVEL: 0.5}
    during_reanalysis = {}
    upgraded.during = lambda analyzed_id: during_reanalysis.update(
        status=library.get_track(analyzed_id).status,
        features={feature.name: feature.analyzer_version for feature in analysis.features_for(analyzed_id)},
    )
    reanalysis = AnalysisService(analysis_unit_of_work, upgraded, media)

    assert reanalysis.enqueue_pending() == 1
    assert reanalysis.process_next().status is AnalysisJobStatus.SUCCEEDED

    assert during_reanalysis["status"] is TrackStatus.READY
    assert set(during_reanalysis["features"].values()) == {"1"}
    track = library.get_track(track_id)
    assert (track.status, track.analysis_version) == (TrackStatus.READY, "test.fake@2")
    features = {feature.name: (feature.value, feature.analyzer_version) for feature in reanalysis.features_for(track_id)}
    assert features == {FeatureName.SAMPLE_PEAK: (0.75, "2"), FeatureName.RMS_LEVEL: (0.5, "2")}
    assert sorted((job.analyzer, job.status.value) for job in reanalysis.list_jobs()) == [
        ("test.fake@1", "SUCCEEDED"),
        ("test.fake@2", "SUCCEEDED"),
    ]


def test_jobs_queued_for_an_old_version_are_superseded(library, analysis, analysis_unit_of_work, media, audio, music):
    _import(library, audio, music, "a.mp3")
    analysis.enqueue_pending()
    current = AnalysisService(analysis_unit_of_work, FakeAnalyzer(version="2"), media)

    stale = current.process_next()

    assert (stale.status, stale.failure_reason, stale.analyzer) == (AnalysisJobStatus.SKIPPED, AnalysisFailureReason.SUPERSEDED, "test.fake@1")
    assert current.enqueue_pending() == 1
    assert current.process_next().status is AnalysisJobStatus.SUCCEEDED


def test_jobs_superseded_by_an_older_analyzer_run_again_under_their_own_version(library, analysis_unit_of_work, media, audio, music):
    """Found in B3 manual verification: a rollback to an older analyzer must not block the newer one forever."""
    _, tracks = _import(library, audio, music, "a.mp3")
    track_id = tracks["a.mp3"].track_id
    newer = AnalysisService(analysis_unit_of_work, FakeAnalyzer(version="2"), media)
    older = AnalysisService(analysis_unit_of_work, FakeAnalyzer(version="1"), media)
    newer.enqueue_pending()

    superseded = older.process_next()
    assert (superseded.status, superseded.failure_reason) == (AnalysisJobStatus.SKIPPED, AnalysisFailureReason.SUPERSEDED)

    assert newer.enqueue_pending() == 1
    finished = newer.process_next()
    assert (finished.status, finished.attempts) == (AnalysisJobStatus.SUCCEEDED, 1)
    assert library.get_track(track_id).analysis_version == "test.fake@2"


# --- The real analyzer ---------------------------------------------------------------


def test_end_to_end_with_the_signal_level_analyzer(library, analysis_unit_of_work, media, audio, music):
    audio.tone(music / "quiet.flac", amplitude=0.25, seconds=1.0)
    audio.tone(music / "loud.wav", amplitude=0.8, seconds=0.5)
    source = library.register_source(str(music))
    library.scan_source(source.source_id)
    analyzer = SignalLevelAnalyzer()
    analysis = AnalysisService(analysis_unit_of_work, analyzer, media)

    assert analysis.enqueue_pending() == 2
    assert analysis.run_until_idle() == 2

    for track in library.list_tracks():
        assert (track.status, track.analysis_version) == (TrackStatus.READY, analyzer.identity.key)
        values = {feature.name: feature.value for feature in analysis.features_for(track.track_id)}
        amplitude, seconds = (0.25, 1.0) if track.original_filename == "quiet.flac" else (0.8, 0.5)
        assert values[FeatureName.DECODED_DURATION_SECONDS] == seconds
        assert values[FeatureName.SAMPLE_PEAK] == pytest.approx(amplitude, abs=1e-3)
        assert values[FeatureName.RMS_LEVEL] == pytest.approx(amplitude / math.sqrt(2), abs=1e-3)


def test_a_corrupt_managed_copy_fails_to_decode_and_records_no_path(library, analysis_unit_of_work, media, audio, music, media_root):
    audio.tone(music / "song.flac")
    source = library.register_source(str(music))
    library.scan_source(source.source_id)
    [track] = library.list_tracks()
    (media_root / f"{track.track_id}.flac").write_bytes(b"corrupted after import" * 100)
    analysis = AnalysisService(analysis_unit_of_work, SignalLevelAnalyzer(), media)
    analysis.enqueue_pending()

    job = analysis.process_next()

    assert (job.status, job.failure_reason) == (AnalysisJobStatus.FAILED, AnalysisFailureReason.DECODE_ERROR)
    assert job.error_message.startswith("The audio could not be decoded:")
    assert track.track_id not in job.error_message
    assert str(media_root) not in job.error_message
    assert library.get_track(track.track_id).status is TrackStatus.IMPORTED
