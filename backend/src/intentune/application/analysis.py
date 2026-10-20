"""Application use cases for background analysis (Prototype 1, phase B3).

AnalysisService owns the job lifecycle; the analyzer only measures (see
ports/analysis.py). It is driven one job at a time by AnalysisWorker
(application/analysis_worker.py), or synchronously by run_until_idle().

- enqueue_pending(): create a job for every available track the current
  analyzer has not analyzed yet. Idempotent: a track and analyzer pair has at
  most one job (also enforced by the database). This is the import pipeline's
  last step, "queue deeper analysis". It runs as a sweep instead of inside
  the import, so it also covers tracks imported before B3, tracks repaired
  after their managed copy went missing, and a new analyzer version.
- recover_interrupted(): run before a worker starts. A RUNNING job left by a
  stopped process goes back to PENDING, or FAILED once its attempts are used up.
- process_next(): claim the oldest PENDING job, analyze outside any database
  transaction, and record the outcome in one short transaction.

A track stays playable throughout. Its status is ANALYZING only during its
first analysis. A READY track being re-analyzed stays READY with its earlier
features until the new ones replace them. A failed or skipped analysis
returns the track to the status it had before.

Error messages recorded on jobs are built from exception types and OS error
text only, never from file paths, so they are safe to show later.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Optional, Sequence

from src.intentune.domain.analysis import (
    AnalysisFailureReason,
    AnalysisJob,
    AnalysisJobKind,
    AnalysisJobStatus,
    AudioDecodeError,
    TrackFeature,
    features_from_result,
    needs_analysis,
    new_analysis_job,
)
from src.intentune.domain.library import Track, TrackStatus
from src.intentune.ports.analysis import AudioAnalyzer
from src.intentune.ports.library_files import ManagedMedia
from src.intentune.ports.unit_of_work import UnitOfWork

logger = logging.getLogger("intentune.analysis")


@dataclass(frozen=True)
class AnalysisPolicy:
    """How many times one job may be attempted (read errors and interruptions both count)."""

    max_attempts: int = 3

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int) or self.max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _os_error_message(error: OSError) -> str:
    return f"The managed copy could not be read ({error.strerror or type(error).__name__})."


class AnalysisService:
    def __init__(
        self,
        unit_of_work: UnitOfWork,
        analyzer: AudioAnalyzer,
        media: ManagedMedia,
        policy: AnalysisPolicy = AnalysisPolicy(),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._uow = unit_of_work
        self._analyzer = analyzer
        self._media = media
        self._policy = policy
        self._clock = clock

    # --- Queue --------------------------------------------------------------------

    def enqueue_pending(self) -> int:
        """Queue every available track the current analyzer has not analyzed. Returns how many jobs were queued."""
        identity = self._analyzer.identity
        now = self._clock()
        queued = 0
        with self._uow:
            jobs = {
                job.track_id: job
                for job in self._uow.analysis_jobs.list_for_analyzer(AnalysisJobKind.ANALYZE_AUDIO, identity.key)
            }
            for track in self._uow.tracks.list_all():
                if not needs_analysis(track, identity):
                    continue
                job = jobs.get(track.track_id)
                if job is None:
                    self._uow.analysis_jobs.add(new_analysis_job(track.track_id, identity, now))
                    queued += 1
                elif job.can_be_requeued:
                    self._uow.analysis_jobs.save(job.requeued(now))
                    queued += 1
            if queued:
                self._uow.commit()
        return queued

    def recover_interrupted(self) -> int:
        """Release jobs a stopped process left RUNNING. Call only when no worker is running. Returns how many."""
        now = self._clock()
        with self._uow:
            running = self._uow.analysis_jobs.list_all(AnalysisJobStatus.RUNNING)
            for job in running:
                self._uow.analysis_jobs.save(job.after_interruption(self._policy.max_attempts, now))
            for track in self._uow.tracks.list_all():
                if track.status is TrackStatus.ANALYZING:
                    self._uow.tracks.save(track.with_status(track.available_status, now))
            self._uow.commit()
        if running:
            logger.info("Recovered %d interrupted analysis job(s)", len(running))
        return len(running)

    # --- Processing -----------------------------------------------------------------

    def process_next(self) -> Optional[AnalysisJob]:
        """Claim and run the oldest pending job. Returns the job as it finished, or None if nothing was pending."""
        now = self._clock()
        with self._uow:
            job = self._uow.analysis_jobs.claim_next(now)
            if job is None:
                return None
            track = self._uow.tracks.get(job.track_id)
            if track is not None and track.status is TrackStatus.IMPORTED:
                self._uow.tracks.save(track.with_status(TrackStatus.ANALYZING, now))
            self._uow.commit()
        return self._run(job, track)

    def run_until_idle(self, limit: Optional[int] = None) -> int:
        """Process jobs until none is pending (or limit is reached). Returns how many were processed."""
        processed = 0
        while limit is None or processed < limit:
            if self.process_next() is None:
                break
            processed += 1
        return processed

    # --- Reading ------------------------------------------------------------------

    def list_jobs(self, status: Optional[AnalysisJobStatus] = None) -> List[AnalysisJob]:
        with self._uow:
            return self._uow.analysis_jobs.list_all(status)

    def features_for(self, track_id: str) -> List[TrackFeature]:
        with self._uow:
            return self._uow.track_features.list_for_track(track_id)

    # --- Internals ------------------------------------------------------------------

    def _run(self, job: AnalysisJob, track: Optional[Track]) -> AnalysisJob:
        identity = self._analyzer.identity
        if track is None:  # foreign keys prevent this; nothing deletes tracks in Prototype 1
            return self._finish(job.failed(AnalysisFailureReason.ANALYZER_ERROR, self._clock(), "The track no longer exists."))
        if job.analyzer != identity.key:
            return self._finish(job.skipped(AnalysisFailureReason.SUPERSEDED, self._clock(), f"Queued for {job.analyzer}."))
        if not self._analyzer.supports(track.audio_format):
            return self._finish(
                job.skipped(
                    AnalysisFailureReason.FORMAT_NOT_SUPPORTED,
                    self._clock(),
                    f"{identity.name} cannot decode {track.audio_format.value} audio.",
                )
            )
        if not self._media.exists(track.track_id, track.audio_format):
            return self._finish(
                job.failed(AnalysisFailureReason.MISSING_MANAGED_FILE, self._clock(), "The managed copy is missing."),
                missing=True,
            )

        try:
            result = self._analyzer.analyze(self._media.path(track.track_id, track.audio_format), track.audio_format)
        except AudioDecodeError as error:
            return self._finish(job.failed(AnalysisFailureReason.DECODE_ERROR, self._clock(), str(error)))
        except OSError as error:
            message = _os_error_message(error)
            if job.attempts < self._policy.max_attempts:
                return self._finish(job.retry_later(AnalysisFailureReason.IO_ERROR, self._clock(), message))
            return self._finish(job.failed(AnalysisFailureReason.IO_ERROR, self._clock(), message))
        except Exception as error:  # one broken track must not stop the worker (guide §6)
            logger.exception("Analyzer error on job %s", job.job_id)
            return self._finish(
                job.failed(AnalysisFailureReason.ANALYZER_ERROR, self._clock(), f"Unexpected {type(error).__name__}.")
            )

        now = self._clock()
        return self._finish(job.succeeded(now), features=features_from_result(result, identity, now))

    def _finish(
        self,
        finished: AnalysisJob,
        features: Optional[Sequence[TrackFeature]] = None,
        missing: bool = False,
    ) -> AnalysisJob:
        """Record a job's outcome, its features, and the track's resulting status in one transaction."""
        now = finished.updated_at
        with self._uow:
            self._uow.analysis_jobs.save(finished)
            track = self._uow.tracks.get(finished.track_id)
            if track is not None:
                if features is not None:
                    self._uow.track_features.replace_for_analyzer(track.track_id, self._analyzer.identity.name, features)
                    updated = track.with_analysis(self._analyzer.identity.key, now)
                elif missing:
                    updated = track.with_status(TrackStatus.MISSING_MANAGED_FILE, now)
                elif track.status is TrackStatus.ANALYZING:
                    updated = track.with_status(track.available_status, now)
                else:
                    updated = track
                if updated != track:
                    self._uow.tracks.save(updated)
            self._uow.commit()
        return finished
