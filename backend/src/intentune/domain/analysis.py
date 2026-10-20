"""Background audio analysis (Prototype 1, phase B3): jobs, measured features, and their rules.

Analysis runs in the background on persisted jobs (D26, D28). Every job
belongs to one track and one analyzer version, so the queue is idempotent:
queuing the same track for the same analyzer twice does nothing, and a new
analyzer version re-analyzes the library by creating new jobs.

Job lifecycle:

    PENDING --claim--> RUNNING --> SUCCEEDED
                          |------> SKIPPED   (the analyzer cannot handle this track, or the job is for an old analyzer)
                          |------> FAILED    (decode error, analyzer error, missing file, or retries used up)
                          '------> PENDING   (a retryable read error; or recovery after the process stopped mid-job)

Attempts are counted when a job is claimed, so a job whose track keeps
interrupting the process still runs out of attempts. A job stopped by a
condition outside its analyzer is queued again by that analyzer: one failed
because the managed copy was missing (once the track is available), and one
skipped because a different analyzer version was running (once its own
version runs again).

Features are measurements with provenance (D20): which analyzer produced them,
which version, when, and, for estimates, a confidence. Exact measurements have
no confidence (None). Nothing here infers semantic or perceptual qualities
such as energy, mood, or danceability (D21).

Pure: no threads, files, or database code.
"""

import math
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Mapping, Optional, Tuple

from src.intentune.domain.library import Track, TrackStatus
from src.intentune.domain.validation import (
    new_uuid,
    optional_text,
    optional_utc_datetime,
    require_canonical_uuid,
    require_non_negative_int,
    require_text,
    require_utc_datetime,
)

_MAX_ERROR_MESSAGE = 500


class AnalysisJobKind(str, Enum):
    ANALYZE_AUDIO = "ANALYZE_AUDIO"


class AnalysisJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AnalysisFailureReason(str, Enum):
    FORMAT_NOT_SUPPORTED = "FORMAT_NOT_SUPPORTED"  # SKIPPED: the analyzer cannot decode this format
    SUPERSEDED = "SUPERSEDED"  # SKIPPED: the job was queued for an analyzer version no longer in use
    DECODE_ERROR = "DECODE_ERROR"  # FAILED: the audio could not be decoded; not retried for this version
    IO_ERROR = "IO_ERROR"  # retried, then FAILED: the managed copy could not be read
    MISSING_MANAGED_FILE = "MISSING_MANAGED_FILE"  # FAILED; queued again once the track is repaired
    INTERRUPTED = "INTERRUPTED"  # FAILED: the process stopped during every allowed attempt
    ANALYZER_ERROR = "ANALYZER_ERROR"  # FAILED: an unexpected error inside the analyzer


_SKIP_REASONS = frozenset({AnalysisFailureReason.FORMAT_NOT_SUPPORTED, AnalysisFailureReason.SUPERSEDED})


class FeatureName(str, Enum):
    """Measured features. All are exact properties of the decoded signal (see adapters/signal_levels.py)."""

    DECODED_DURATION_SECONDS = "decoded_duration_seconds"
    SAMPLE_PEAK = "sample_peak"
    RMS_LEVEL = "rms_level"


class AudioDecodeError(Exception):
    """The audio content could not be decoded. Deterministic for a given file and analyzer, so not retried."""


def _short_message(value: Optional[str]) -> Optional[str]:
    message = optional_text(value, "error_message")
    return message[:_MAX_ERROR_MESSAGE] if message is not None else None


@dataclass(frozen=True)
class AnalyzerIdentity:
    """Which analyzer produced a result. A change of version means previous results are out of date."""

    name: str
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_text(self.name, "name"))
        object.__setattr__(self, "version", require_text(self.version, "version"))
        if "@" in self.name:
            raise ValueError("an analyzer name must not contain '@'")

    @property
    def key(self) -> str:
        """name@version: stored on jobs and as a track's analysis_version."""
        return f"{self.name}@{self.version}"


@dataclass(frozen=True)
class AnalysisResult:
    """What an analyzer measured for one track: a value per feature."""

    values: Mapping[FeatureName, float]

    def __post_init__(self) -> None:
        values = {}
        for name, value in dict(self.values).items():
            values[FeatureName(name)] = _require_feature_value(value, f"{FeatureName(name).value}")
        if not values:
            raise ValueError("an analysis result needs at least one feature")
        object.__setattr__(self, "values", values)


def _require_feature_value(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be a finite, non-negative number")
    return float(value)


@dataclass(frozen=True)
class TrackFeature:
    """One measured feature of one track, with provenance."""

    name: FeatureName
    value: float
    analyzer_name: str
    analyzer_version: str
    computed_at: datetime
    confidence: Optional[float] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", FeatureName(self.name))
        object.__setattr__(self, "value", _require_feature_value(self.value, "value"))
        object.__setattr__(self, "analyzer_name", require_text(self.analyzer_name, "analyzer_name"))
        object.__setattr__(self, "analyzer_version", require_text(self.analyzer_version, "analyzer_version"))
        object.__setattr__(self, "computed_at", require_utc_datetime(self.computed_at, "computed_at"))
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
                raise ValueError("confidence must be a number")
            if not 0.0 <= self.confidence <= 1.0:
                raise ValueError("confidence must be between 0.0 and 1.0")
            object.__setattr__(self, "confidence", float(self.confidence))


def features_from_result(
    result: AnalysisResult, analyzer: AnalyzerIdentity, computed_at: datetime
) -> Tuple[TrackFeature, ...]:
    """The result's values as TrackFeature rows attributed to analyzer. Measurements carry no confidence."""
    return tuple(
        TrackFeature(
            name=name,
            value=value,
            analyzer_name=analyzer.name,
            analyzer_version=analyzer.version,
            computed_at=computed_at,
        )
        for name, value in sorted(result.values.items(), key=lambda item: item[0].value)
    )


@dataclass(frozen=True)
class AnalysisJob:
    job_id: str
    track_id: str
    kind: AnalysisJobKind
    analyzer: str
    status: AnalysisJobStatus
    attempts: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    failure_reason: Optional[AnalysisFailureReason] = None
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        require_canonical_uuid(self.job_id, "job_id")
        require_canonical_uuid(self.track_id, "track_id")
        object.__setattr__(self, "kind", AnalysisJobKind(self.kind))
        object.__setattr__(self, "analyzer", require_text(self.analyzer, "analyzer"))
        object.__setattr__(self, "status", AnalysisJobStatus(self.status))
        require_non_negative_int(self.attempts, "attempts")
        object.__setattr__(self, "created_at", require_utc_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", require_utc_datetime(self.updated_at, "updated_at"))
        object.__setattr__(self, "started_at", optional_utc_datetime(self.started_at, "started_at"))
        object.__setattr__(self, "finished_at", optional_utc_datetime(self.finished_at, "finished_at"))
        if self.failure_reason is not None:
            object.__setattr__(self, "failure_reason", AnalysisFailureReason(self.failure_reason))
        object.__setattr__(self, "error_message", _short_message(self.error_message))

        if self.status is AnalysisJobStatus.SUCCEEDED and self.failure_reason is not None:
            raise ValueError("a SUCCEEDED job has no failure_reason")
        if self.status in (AnalysisJobStatus.FAILED, AnalysisJobStatus.SKIPPED) and self.failure_reason is None:
            raise ValueError(f"a {self.status.value} job needs a failure_reason")
        if self.status is AnalysisJobStatus.SKIPPED and self.failure_reason not in _SKIP_REASONS:
            raise ValueError("a SKIPPED job's reason must be FORMAT_NOT_SUPPORTED or SUPERSEDED")
        if self.status is AnalysisJobStatus.FAILED and self.failure_reason in _SKIP_REASONS:
            raise ValueError("FORMAT_NOT_SUPPORTED and SUPERSEDED are reasons to skip, not to fail")
        if self.status is AnalysisJobStatus.RUNNING and (self.started_at is None or self.attempts < 1):
            raise ValueError("a RUNNING job has been claimed: it needs started_at and at least one attempt")

    # Transitions. Claiming (PENDING -> RUNNING, attempts + 1) happens atomically in the repository.

    def succeeded(self, now: datetime) -> "AnalysisJob":
        return self._finished(AnalysisJobStatus.SUCCEEDED, None, None, now)

    def skipped(self, reason: AnalysisFailureReason, now: datetime, message: Optional[str] = None) -> "AnalysisJob":
        return self._finished(AnalysisJobStatus.SKIPPED, reason, message, now)

    def failed(self, reason: AnalysisFailureReason, now: datetime, message: Optional[str] = None) -> "AnalysisJob":
        return self._finished(AnalysisJobStatus.FAILED, reason, message, now)

    def retry_later(self, reason: AnalysisFailureReason, now: datetime, message: Optional[str] = None) -> "AnalysisJob":
        """Back to PENDING; the reason and message of this attempt stay visible until the next one."""
        return replace(
            self,
            status=AnalysisJobStatus.PENDING,
            failure_reason=reason,
            error_message=message,
            finished_at=None,
            updated_at=now,
        )

    def after_interruption(self, max_attempts: int, now: datetime) -> "AnalysisJob":
        """A RUNNING job found when no worker is running: the process stopped during it."""
        if self.attempts >= max_attempts:
            return self.failed(AnalysisFailureReason.INTERRUPTED, now, "The process stopped during every attempt.")
        return self.retry_later(AnalysisFailureReason.INTERRUPTED, now, "The process stopped during the previous attempt.")

    def requeued(self, now: datetime) -> "AnalysisJob":
        """A fresh start for a job that failed for a reason that no longer applies."""
        return replace(
            self,
            status=AnalysisJobStatus.PENDING,
            attempts=0,
            started_at=None,
            finished_at=None,
            failure_reason=None,
            error_message=None,
            updated_at=now,
        )

    @property
    def can_be_requeued(self) -> bool:
        """True for a job stopped by a condition outside its own analyzer, which its analyzer may retry.

        - FAILED, MISSING_MANAGED_FILE: the copy was missing; the track is now available again.
        - SKIPPED, SUPERSEDED: a different analyzer version was running (for example after a
          rollback); this job's own version is running now.
        """
        return (self.status, self.failure_reason) in (
            (AnalysisJobStatus.FAILED, AnalysisFailureReason.MISSING_MANAGED_FILE),
            (AnalysisJobStatus.SKIPPED, AnalysisFailureReason.SUPERSEDED),
        )

    def _finished(self, status, reason, message, now) -> "AnalysisJob":
        return replace(self, status=status, failure_reason=reason, error_message=message, finished_at=now, updated_at=now)


def new_analysis_job(track_id: str, analyzer: AnalyzerIdentity, now: datetime) -> AnalysisJob:
    return AnalysisJob(
        job_id=new_uuid(),
        track_id=track_id,
        kind=AnalysisJobKind.ANALYZE_AUDIO,
        analyzer=analyzer.key,
        status=AnalysisJobStatus.PENDING,
        attempts=0,
        created_at=now,
        updated_at=now,
    )


def needs_analysis(track: Track, analyzer: AnalyzerIdentity) -> bool:
    """Whether this analyzer should (re)analyze the track: available, not being analyzed, and not done by this version."""
    return track.status in (TrackStatus.IMPORTED, TrackStatus.READY) and track.analysis_version != analyzer.key
