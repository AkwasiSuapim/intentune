"""Analysis ports: the analyzer itself, and storage for jobs and measured features.

The analyzer is deliberately separate from the job system. AudioAnalyzer only
turns one audio file into measurements; queuing, retries, recovery, and
recording results belong to the application layer (application/analysis.py).
Implemented by src/intentune/adapters/signal_levels.py and
src/intentune/persistence/repositories.py.
"""

from datetime import datetime
from typing import List, Optional, Protocol, Sequence

from src.intentune.domain.analysis import AnalysisJob, AnalysisJobKind, AnalysisJobStatus, AnalysisResult, AnalyzerIdentity, TrackFeature
from src.intentune.domain.library import AudioFormat


class AudioAnalyzer(Protocol):
    @property
    def identity(self) -> AnalyzerIdentity:
        """Name and version. Results from another version are out of date."""
        ...

    def supports(self, audio_format: AudioFormat) -> bool:
        """Whether this analyzer can decode the format at all."""
        ...

    def analyze(self, path: str, audio_format: AudioFormat) -> AnalysisResult:
        """Measure one file. Raises AudioDecodeError for undecodable content, OSError if it cannot be read."""
        ...


class AnalysisJobRepository(Protocol):
    def get(self, job_id: str) -> Optional[AnalysisJob]:
        ...

    def list_all(self, status: Optional[AnalysisJobStatus] = None) -> List[AnalysisJob]:
        """Jobs, oldest first, optionally only those with one status."""
        ...

    def list_for_analyzer(self, kind: AnalysisJobKind, analyzer: str) -> List[AnalysisJob]:
        """Every job of one kind for one analyzer key (name@version)."""
        ...

    def add(self, job: AnalysisJob) -> None:
        ...

    def save(self, job: AnalysisJob) -> None:
        ...

    def claim_next(self, now: datetime) -> Optional[AnalysisJob]:
        """Atomically move the oldest PENDING job to RUNNING, counting an attempt. None if nothing is pending."""
        ...


class TrackFeatureRepository(Protocol):
    def list_for_track(self, track_id: str) -> List[TrackFeature]:
        ...

    def replace_for_analyzer(self, track_id: str, analyzer_name: str, features: Sequence[TrackFeature]) -> None:
        """Replace this analyzer's features for the track (any version) with features."""
        ...
