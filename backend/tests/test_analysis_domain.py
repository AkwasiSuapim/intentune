"""Analysis domain rules: job transitions and invariants, recovery, the needs-analysis rule, and feature validation."""

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.intentune.application.analysis import AnalysisPolicy
from src.intentune.domain.analysis import (
    AnalysisFailureReason,
    AnalysisJob,
    AnalysisJobKind,
    AnalysisJobStatus,
    AnalysisResult,
    AnalyzerIdentity,
    FeatureName,
    TrackFeature,
    features_from_result,
    needs_analysis,
    new_analysis_job,
)
from src.intentune.domain.library import AudioFormat, Track, TrackStatus

_NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
_LATER = _NOW + timedelta(minutes=1)
_TRACK_ID = "3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e"
_ANALYZER = AnalyzerIdentity(name="test.analyzer", version="1")


def _job(**overrides):
    return replace(new_analysis_job(_TRACK_ID, _ANALYZER, _NOW), **overrides)


def _running(attempts=1):
    return _job(status=AnalysisJobStatus.RUNNING, attempts=attempts, started_at=_NOW)


def _track(**overrides):
    values = dict(
        track_id=_TRACK_ID,
        sha256="a" * 64,
        size_bytes=10,
        audio_format=AudioFormat.FLAC,
        status=TrackStatus.IMPORTED,
        original_filename="song.flac",
        created_at=_NOW,
        updated_at=_NOW,
    )
    values.update(overrides)
    return Track(**values)


# --- Analyzer identity and results -------------------------------------------------


def test_analyzer_key_combines_name_and_version():
    assert _ANALYZER.key == "test.analyzer@1"


@pytest.mark.parametrize("name, version", [("", "1"), ("a", " "), ("a@b", "1")])
def test_analyzer_identity_rejects_invalid_parts(name, version):
    with pytest.raises(ValueError):
        AnalyzerIdentity(name=name, version=version)


@pytest.mark.parametrize("value", [-0.1, math.inf, math.nan, True, "0.5"])
def test_feature_values_must_be_finite_and_non_negative(value):
    with pytest.raises(ValueError):
        AnalysisResult(values={FeatureName.SAMPLE_PEAK: value})


def test_a_result_needs_at_least_one_known_feature():
    with pytest.raises(ValueError):
        AnalysisResult(values={})
    with pytest.raises(ValueError):
        AnalysisResult(values={"tempo_bpm": 120.0})


def test_features_from_result_carry_provenance_and_no_confidence():
    result = AnalysisResult(values={FeatureName.RMS_LEVEL: 0.25, FeatureName.SAMPLE_PEAK: 1.02})

    features = features_from_result(result, _ANALYZER, _NOW)

    assert [(feature.name, feature.value) for feature in features] == [(FeatureName.RMS_LEVEL, 0.25), (FeatureName.SAMPLE_PEAK, 1.02)]
    assert all(
        (feature.analyzer_name, feature.analyzer_version, feature.computed_at, feature.confidence) == ("test.analyzer", "1", _NOW, None)
        for feature in features
    )


@pytest.mark.parametrize("confidence", [-0.01, 1.01, True])
def test_track_feature_confidence_must_be_a_fraction(confidence):
    with pytest.raises(ValueError):
        TrackFeature(FeatureName.RMS_LEVEL, 0.1, "a", "1", _NOW, confidence=confidence)


# --- Jobs ------------------------------------------------------------------------


def test_a_new_job_is_pending_with_no_attempts():
    job = new_analysis_job(_TRACK_ID, _ANALYZER, _NOW)

    assert (job.kind, job.analyzer, job.status, job.attempts) == (AnalysisJobKind.ANALYZE_AUDIO, "test.analyzer@1", AnalysisJobStatus.PENDING, 0)
    assert (job.started_at, job.finished_at, job.failure_reason) == (None, None, None)


def test_success_clears_any_previous_failure():
    job = _running().retry_later(AnalysisFailureReason.IO_ERROR, _NOW, "busy")
    claimed = replace(job, status=AnalysisJobStatus.RUNNING, attempts=2)

    done = claimed.succeeded(_LATER)

    assert (done.status, done.failure_reason, done.error_message, done.finished_at) == (AnalysisJobStatus.SUCCEEDED, None, None, _LATER)


@pytest.mark.parametrize("reason", [AnalysisFailureReason.FORMAT_NOT_SUPPORTED, AnalysisFailureReason.SUPERSEDED])
def test_skip_reasons(reason):
    assert _running().skipped(reason, _LATER).status is AnalysisJobStatus.SKIPPED
    with pytest.raises(ValueError):
        _running().failed(reason, _LATER)


@pytest.mark.parametrize("reason", [reason for reason in AnalysisFailureReason if reason not in (AnalysisFailureReason.FORMAT_NOT_SUPPORTED, AnalysisFailureReason.SUPERSEDED)])
def test_failure_reasons_cannot_be_used_to_skip(reason):
    assert _running().failed(reason, _LATER).status is AnalysisJobStatus.FAILED
    with pytest.raises(ValueError):
        _running().skipped(reason, _LATER)


def test_retry_later_returns_to_pending_and_keeps_the_reason_visible():
    job = _running(attempts=1).retry_later(AnalysisFailureReason.IO_ERROR, _LATER, "The managed copy could not be read.")

    assert (job.status, job.attempts, job.failure_reason, job.finished_at) == (AnalysisJobStatus.PENDING, 1, AnalysisFailureReason.IO_ERROR, None)


def test_interruption_retries_until_attempts_run_out():
    policy = AnalysisPolicy(max_attempts=2)

    first = _running(attempts=1).after_interruption(policy.max_attempts, _LATER)
    last = _running(attempts=2).after_interruption(policy.max_attempts, _LATER)

    assert (first.status, first.failure_reason) == (AnalysisJobStatus.PENDING, AnalysisFailureReason.INTERRUPTED)
    assert (last.status, last.failure_reason) == (AnalysisJobStatus.FAILED, AnalysisFailureReason.INTERRUPTED)


def test_only_jobs_stopped_by_outside_conditions_can_be_requeued():
    missing = _running().failed(AnalysisFailureReason.MISSING_MANAGED_FILE, _LATER)
    superseded = _running().skipped(AnalysisFailureReason.SUPERSEDED, _LATER)
    not_requeueable = [
        _running().failed(reason, _LATER)
        for reason in (AnalysisFailureReason.DECODE_ERROR, AnalysisFailureReason.IO_ERROR, AnalysisFailureReason.INTERRUPTED, AnalysisFailureReason.ANALYZER_ERROR)
    ] + [_running().skipped(AnalysisFailureReason.FORMAT_NOT_SUPPORTED, _LATER), _running().succeeded(_LATER), _job()]

    assert missing.can_be_requeued and superseded.can_be_requeued
    assert not any(job.can_be_requeued for job in not_requeueable)
    requeued = missing.requeued(_LATER)
    assert (requeued.status, requeued.attempts, requeued.failure_reason, requeued.started_at) == (AnalysisJobStatus.PENDING, 0, None, None)


@pytest.mark.parametrize(
    "overrides",
    [
        dict(status=AnalysisJobStatus.SUCCEEDED, failure_reason=AnalysisFailureReason.IO_ERROR),
        dict(status=AnalysisJobStatus.FAILED),
        dict(status=AnalysisJobStatus.SKIPPED),
        dict(status=AnalysisJobStatus.RUNNING, attempts=1),
        dict(status=AnalysisJobStatus.RUNNING, started_at=_NOW, attempts=0),
        dict(attempts=-1),
        dict(analyzer=" "),
        dict(track_id="track"),
    ],
)
def test_job_invariants(overrides):
    with pytest.raises(ValueError):
        _job(**overrides)


def test_long_error_messages_are_truncated():
    job = _running().failed(AnalysisFailureReason.ANALYZER_ERROR, _LATER, "x" * 2000)

    assert len(job.error_message) == 500


@pytest.mark.parametrize("value", [0, -1, True])
def test_policy_requires_at_least_one_attempt(value):
    with pytest.raises(ValueError):
        AnalysisPolicy(max_attempts=value)


# --- Which tracks need analysis ----------------------------------------------------


@pytest.mark.parametrize(
    "status, analysis_version, expected",
    [
        (TrackStatus.IMPORTED, None, True),
        (TrackStatus.READY, "test.analyzer@0", True),
        (TrackStatus.READY, "test.analyzer@1", False),
        (TrackStatus.ANALYZING, None, False),
        (TrackStatus.MISSING_MANAGED_FILE, None, False),
    ],
)
def test_needs_analysis(status, analysis_version, expected):
    assert needs_analysis(_track(status=status, analysis_version=analysis_version), _ANALYZER) is expected


def test_available_status_depends_on_whether_the_track_was_analyzed():
    assert _track().available_status is TrackStatus.IMPORTED
    assert _track(analysis_version="test.analyzer@1").available_status is TrackStatus.READY


def test_with_analysis_marks_the_track_ready_unless_its_copy_is_missing():
    ready = _track(status=TrackStatus.ANALYZING).with_analysis("test.analyzer@1", _LATER)
    missing = _track(status=TrackStatus.MISSING_MANAGED_FILE).with_analysis("test.analyzer@1", _LATER)

    assert (ready.status, ready.analysis_version, ready.updated_at) == (TrackStatus.READY, "test.analyzer@1", _LATER)
    assert (missing.status, missing.analysis_version) == (TrackStatus.MISSING_MANAGED_FILE, "test.analyzer@1")
