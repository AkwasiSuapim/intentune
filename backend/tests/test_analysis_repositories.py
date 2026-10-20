"""SQLite analysis repositories against a migrated database: jobs, the atomic claim, features, and constraints."""

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.intentune.domain.analysis import (
    AnalysisFailureReason,
    AnalysisJobKind,
    AnalysisJobStatus,
    AnalyzerIdentity,
    FeatureName,
    TrackFeature,
    new_analysis_job,
)
from src.intentune.domain.library import AudioFormat, Track, TrackStatus

_NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
_V1 = AnalyzerIdentity(name="test.analyzer", version="1")
_V2 = AnalyzerIdentity(name="test.analyzer", version="2")


def _add_track(unit_of_work, sha_char="a"):
    track = Track(
        track_id=str(uuid.uuid4()),
        sha256=sha_char * 64,
        size_bytes=10,
        audio_format=AudioFormat.FLAC,
        status=TrackStatus.IMPORTED,
        original_filename="song.flac",
        created_at=_NOW,
        updated_at=_NOW,
    )
    with unit_of_work:
        unit_of_work.tracks.add(track)
        unit_of_work.commit()
    return track


def _add_jobs(unit_of_work, *jobs):
    with unit_of_work:
        for job in jobs:
            unit_of_work.analysis_jobs.add(job)
        unit_of_work.commit()


def _feature(name, value, analyzer=_V1, computed_at=_NOW):
    return TrackFeature(name, value, analyzer.name, analyzer.version, computed_at)


# --- Jobs ------------------------------------------------------------------------


def test_job_round_trip(unit_of_work):
    track = _add_track(unit_of_work)
    job = new_analysis_job(track.track_id, _V1, _NOW)
    _add_jobs(unit_of_work, job)
    failed = replace(job, status=AnalysisJobStatus.RUNNING, attempts=1, started_at=_NOW).failed(
        AnalysisFailureReason.DECODE_ERROR, _NOW + timedelta(seconds=3), "The audio could not be decoded."
    )

    with unit_of_work:
        assert unit_of_work.analysis_jobs.get(job.job_id) == job
        unit_of_work.analysis_jobs.save(failed)
        unit_of_work.commit()

    with unit_of_work:
        assert unit_of_work.analysis_jobs.get(job.job_id) == failed
        assert unit_of_work.analysis_jobs.get(str(uuid.uuid4())) is None


def test_list_all_filters_by_status_oldest_first(unit_of_work):
    first, second = _add_track(unit_of_work, "a"), _add_track(unit_of_work, "b")
    older = new_analysis_job(first.track_id, _V1, _NOW)
    newer = new_analysis_job(second.track_id, _V1, _NOW + timedelta(seconds=1))
    done = replace(
        new_analysis_job(first.track_id, _V2, _NOW + timedelta(milliseconds=500)),
        status=AnalysisJobStatus.SKIPPED,
        failure_reason=AnalysisFailureReason.SUPERSEDED,
    )
    _add_jobs(unit_of_work, newer, done, older)

    with unit_of_work:
        assert [job.job_id for job in unit_of_work.analysis_jobs.list_all()] == [older.job_id, done.job_id, newer.job_id]
        assert [job.job_id for job in unit_of_work.analysis_jobs.list_all(AnalysisJobStatus.PENDING)] == [older.job_id, newer.job_id]
        assert [job.job_id for job in unit_of_work.analysis_jobs.list_for_analyzer(AnalysisJobKind.ANALYZE_AUDIO, _V2.key)] == [done.job_id]


def test_one_job_per_track_kind_and_analyzer_version(unit_of_work):
    track = _add_track(unit_of_work)
    _add_jobs(unit_of_work, new_analysis_job(track.track_id, _V1, _NOW), new_analysis_job(track.track_id, _V2, _NOW))

    with pytest.raises(IntegrityError):
        _add_jobs(unit_of_work, new_analysis_job(track.track_id, _V1, _NOW))


def test_jobs_must_belong_to_an_existing_track(unit_of_work):
    with pytest.raises(IntegrityError):
        _add_jobs(unit_of_work, new_analysis_job(str(uuid.uuid4()), _V1, _NOW))


def test_claim_next_takes_the_oldest_pending_job_and_counts_an_attempt(unit_of_work):
    first, second = _add_track(unit_of_work, "a"), _add_track(unit_of_work, "b")
    older = new_analysis_job(first.track_id, _V1, _NOW)
    newer = new_analysis_job(second.track_id, _V1, _NOW + timedelta(seconds=1))
    _add_jobs(unit_of_work, newer, older)
    claimed_at = _NOW + timedelta(minutes=5)

    with unit_of_work:
        claimed = unit_of_work.analysis_jobs.claim_next(claimed_at)
        unit_of_work.commit()

    assert claimed.job_id == older.job_id
    assert (claimed.status, claimed.attempts, claimed.started_at, claimed.updated_at) == (AnalysisJobStatus.RUNNING, 1, claimed_at, claimed_at)
    with unit_of_work:
        assert unit_of_work.analysis_jobs.get(older.job_id) == claimed
        assert unit_of_work.analysis_jobs.get(newer.job_id).status is AnalysisJobStatus.PENDING


def test_claim_clears_the_previous_attempts_failure(unit_of_work):
    track = _add_track(unit_of_work)
    retried = replace(new_analysis_job(track.track_id, _V1, _NOW), attempts=1, failure_reason=AnalysisFailureReason.IO_ERROR, error_message="busy")
    _add_jobs(unit_of_work, retried)

    with unit_of_work:
        claimed = unit_of_work.analysis_jobs.claim_next(_NOW)
        unit_of_work.commit()

    assert (claimed.attempts, claimed.failure_reason, claimed.error_message) == (2, None, None)


def test_claim_next_never_takes_jobs_that_are_not_pending(unit_of_work):
    track = _add_track(unit_of_work)
    _add_jobs(
        unit_of_work,
        replace(new_analysis_job(track.track_id, _V1, _NOW), status=AnalysisJobStatus.RUNNING, attempts=1, started_at=_NOW),
    )

    with unit_of_work:
        assert unit_of_work.analysis_jobs.claim_next(_NOW) is None


def test_a_job_is_claimed_only_once(session_factory, unit_of_work):
    from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork

    track = _add_track(unit_of_work)
    _add_jobs(unit_of_work, new_analysis_job(track.track_id, _V1, _NOW))
    other = SqlAlchemyUnitOfWork(session_factory)

    with unit_of_work:
        first = unit_of_work.analysis_jobs.claim_next(_NOW)
        unit_of_work.commit()
    with other:
        second = other.analysis_jobs.claim_next(_NOW)

    assert first is not None
    assert second is None


# --- Features ----------------------------------------------------------------------


def test_features_round_trip_with_provenance(unit_of_work):
    track = _add_track(unit_of_work)
    features = [_feature(FeatureName.RMS_LEVEL, 0.25), _feature(FeatureName.SAMPLE_PEAK, 0.5)]

    with unit_of_work:
        unit_of_work.track_features.replace_for_analyzer(track.track_id, _V1.name, features)
        unit_of_work.commit()

    with unit_of_work:
        assert unit_of_work.track_features.list_for_track(track.track_id) == features


def test_replacing_features_removes_the_analyzers_earlier_version(unit_of_work):
    track = _add_track(unit_of_work)
    later = _NOW + timedelta(days=1)
    with unit_of_work:
        unit_of_work.track_features.replace_for_analyzer(
            track.track_id, _V1.name, [_feature(FeatureName.RMS_LEVEL, 0.25), _feature(FeatureName.SAMPLE_PEAK, 0.5)]
        )
        unit_of_work.commit()
    replacement = [_feature(FeatureName.RMS_LEVEL, 0.3, analyzer=_V2, computed_at=later)]

    with unit_of_work:
        unit_of_work.track_features.replace_for_analyzer(track.track_id, _V1.name, replacement)
        unit_of_work.commit()

    with unit_of_work:
        assert unit_of_work.track_features.list_for_track(track.track_id) == replacement


def test_replacing_keeps_other_analyzers_features(unit_of_work):
    track = _add_track(unit_of_work)
    other = AnalyzerIdentity(name="other.analyzer", version="1")
    with unit_of_work:
        unit_of_work.track_features.replace_for_analyzer(track.track_id, other.name, [_feature(FeatureName.SAMPLE_PEAK, 0.9, analyzer=other)])
        unit_of_work.track_features.replace_for_analyzer(track.track_id, _V1.name, [_feature(FeatureName.RMS_LEVEL, 0.2)])
        unit_of_work.commit()

    with unit_of_work:
        names = {(feature.name, feature.analyzer_name) for feature in unit_of_work.track_features.list_for_track(track.track_id)}
    assert names == {(FeatureName.SAMPLE_PEAK, "other.analyzer"), (FeatureName.RMS_LEVEL, "test.analyzer")}


def test_replacement_features_must_come_from_that_analyzer(unit_of_work):
    track = _add_track(unit_of_work)
    with unit_of_work:
        with pytest.raises(ValueError):
            unit_of_work.track_features.replace_for_analyzer(
                track.track_id, "other.analyzer", [_feature(FeatureName.RMS_LEVEL, 0.2)]
            )


# --- Database-level rules ----------------------------------------------------------


def _insert_job(connection, track_id, status="PENDING", reason=None, kind="ANALYZE_AUDIO"):
    connection.exec_driver_sql(
        "INSERT INTO analysis_jobs (id, track_id, kind, analyzer, status, attempts, failure_reason, created_at, updated_at) "
        "VALUES (?, ?, ?, 'a@1', ?, 0, ?, '2026-10-20 09:00:00', '2026-10-20 09:00:00')",
        (str(uuid.uuid4()), track_id, kind, status, reason),
    )


@pytest.mark.parametrize("status", [status.value for status in AnalysisJobStatus])
def test_database_accepts_every_domain_job_status(engine, unit_of_work, status):
    track = _add_track(unit_of_work)
    reason = "SUPERSEDED" if status == "SKIPPED" else ("DECODE_ERROR" if status == "FAILED" else None)
    with engine.begin() as connection:
        _insert_job(connection, track.track_id, status=status, reason=reason)


@pytest.mark.parametrize(
    "status, reason, kind",
    [("DONE", None, "ANALYZE_AUDIO"), ("FAILED", None, "ANALYZE_AUDIO"), ("SUCCEEDED", "IO_ERROR", "ANALYZE_AUDIO"), ("PENDING", "CRASHED", "ANALYZE_AUDIO"), ("PENDING", None, "RESCAN_SOURCE")],
)
def test_database_rejects_job_rows_the_domain_does_not_allow(engine, unit_of_work, status, reason, kind):
    track = _add_track(unit_of_work)
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            _insert_job(connection, track.track_id, status=status, reason=reason, kind=kind)


def test_database_rejects_unknown_feature_names(engine, unit_of_work):
    track = _add_track(unit_of_work)
    insert = (
        "INSERT INTO track_features (id, track_id, name, value, analyzer_name, analyzer_version, computed_at) "
        "VALUES (?, ?, ?, 0.5, 'a', '1', '2026-10-20 09:00:00')"
    )
    with engine.begin() as connection:
        for name in FeatureName:
            connection.exec_driver_sql(insert, (str(uuid.uuid4()), track.track_id, name.value))

    for invented in ("energy", "danceability", "tempo_bpm"):
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.exec_driver_sql(insert, (str(uuid.uuid4()), track.track_id, invented))
