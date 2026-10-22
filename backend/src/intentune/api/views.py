"""Domain objects -> response bodies (B8). Pure mapping: nothing is computed here that the domain did not decide.

Occurrences and playlist items show their tracks. Callers load those tracks
first (LibraryService.get_tracks()) and pass them in by id; track_ids_of()
lists which are needed.
"""

from pathlib import PurePath
from typing import Callable, Dict, List, Mapping, Optional, Sequence, TypeVar

from src.intentune.api.schemas import (
    ContextOut,
    EnergyLevelOut,
    FeedbackFactOut,
    MeaningOut,
    DimensionsOut,
    LibraryReadinessOut,
    VocabularyOut,
    FeedbackEventOut,
    FeedbackOut,
    InterpretationOut,
    JobOut,
    OccurrenceOut,
    PlaylistItemOut,
    PlaylistOut,
    PlaylistSummaryOut,
    ScanReportOut,
    SessionDetailOut,
    SessionOut,
    SessionStateOut,
    SourceOut,
    TrackOut,
    TurnOut,
)
from src.intentune.application.feedback import FeedbackOutcome
from src.intentune.domain.analysis import AnalysisJob
from src.intentune.domain.intent import DIMENSIONS, ENERGY_LEVELS, UNMAPPED_CONTEXT_FIELDS, MeaningKind, MessageMeaning, Vocabulary
from src.intentune.domain.library import LabelKind, LibrarySource, ScanReport, Track, TrackStatus
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.playlist import PlaylistContents, PlaylistSummary
from src.intentune.domain.policy import Interpretation
from src.intentune.domain.session import (
    FeedbackEvent,
    ListeningSession,
    RecommendationOccurrence,
    SessionHistory,
    SessionState,
    SessionTurn,
)

_UNNAMED_FOLDER = "Library folder"

T = TypeVar("T")


def _wire(value: Optional[str]) -> Optional[str]:
    return value.lower() if value is not None else None


def audio_url(track_id: str) -> str:
    return f"/api/v1/tracks/{track_id}/audio"


# --- Library -------------------------------------------------------------------------


def track_out(track: Track) -> TrackOut:
    return TrackOut(
        track_id=track.track_id,
        title=track.title,
        file_name=track.original_filename,
        artist=track.artist,
        album=track.album,
        year=track.year,
        duration_seconds=track.duration_seconds,
        format=track.audio_format.value,
        status=_wire(track.status.value),
        playable=track.status is not TrackStatus.MISSING_MANAGED_FILE,
        genres=list(track.genres),
        moods=[label.value for label in track.labels if label.kind is LabelKind.MOOD],
        audio_url=audio_url(track.track_id),
    )


def source_out(source: LibrarySource) -> SourceOut:
    return SourceOut(
        source_id=source.source_id,
        name=PurePath(source.path).name or _UNNAMED_FOLDER,
        status=_wire(source.status.value),
        created_at=source.created_at,
        last_scanned_at=source.last_scanned_at,
    )


def scan_report_out(report: ScanReport) -> ScanReportOut:
    return ScanReportOut(
        source_id=report.source_id,
        source_missing=report.source_missing,
        imported=report.imported,
        duplicates=report.duplicates,
        unchanged=report.unchanged,
        repaired=report.repaired,
        unsupported=report.unsupported,
        failed=report.failed,
        missing=report.missing,
        ignored=report.ignored,
        tag_failures=report.tag_failures,
    )


def job_out(job: AnalysisJob) -> JobOut:
    return JobOut(
        job_id=job.job_id,
        track_id=job.track_id,
        kind=_wire(job.kind.value),
        analyzer=job.analyzer,
        status=_wire(job.status.value),
        attempts=job.attempts,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        failure_reason=_wire(job.failure_reason.value if job.failure_reason is not None else None),
        error_message=job.error_message,
    )


# --- Sessions ------------------------------------------------------------------------


def track_ids_of(state: Optional[SessionState] = None, history: Optional[SessionHistory] = None) -> List[str]:
    """The tracks a session state and history show."""
    occurrences: List[RecommendationOccurrence] = []
    if state is not None:
        occurrences.extend(state.queue)
        if state.playing is not None:
            occurrences.append(state.playing)
    if history is not None:
        occurrences.extend(history.occurrences)
    return [occurrence.track_id for occurrence in occurrences]


def context_out(context: ListeningContext) -> ContextOut:
    return ContextOut(
        current_mood=context.current_mood,
        desired_mood=context.desired_mood,
        listening_goal=context.listening_goal,
        activity=context.activity,
        temporary_genres=list(context.temporary_genres),
        temporary_moods=list(context.temporary_moods),
        target_energy=context.target_energy,
        target_danceability=context.target_danceability,
        target_valence=context.target_valence,
        target_acousticness=context.target_acousticness,
        target_tempo_bpm=context.target_tempo_bpm,
    )


def session_out(session: ListeningSession) -> SessionOut:
    return SessionOut(
        session_id=session.session_id,
        status=_wire(session.status.value),
        context=context_out(session.current_context),
        started_at=session.started_at,
        updated_at=session.updated_at,
        ended_at=session.ended_at,
        end_reason=_wire(session.end_reason.value if session.end_reason is not None else None),
    )


def occurrence_out(occurrence: RecommendationOccurrence, tracks: Mapping[str, Track]) -> OccurrenceOut:
    return OccurrenceOut(
        occurrence_id=occurrence.occurrence_id,
        track=track_out(tracks[occurrence.track_id]),
        status=_wire(occurrence.status.value),
        rank=occurrence.rank,
        score=occurrence.score,
        algorithm=occurrence.algorithm,
        is_exploration=occurrence.is_exploration,
        surfaced_position=occurrence.surfaced_position,
        queue_position=occurrence.queue_position,
        surfaced_at=occurrence.surfaced_at,
        started_at=occurrence.started_at,
        finished_at=occurrence.finished_at,
    )


def session_state_out(state: SessionState, tracks: Mapping[str, Track]) -> SessionStateOut:
    return SessionStateOut(
        session=session_out(state.session),
        playing=occurrence_out(state.playing, tracks) if state.playing is not None else None,
        queue=[occurrence_out(occurrence, tracks) for occurrence in state.queue],
    )


def turn_out(turn: SessionTurn) -> TurnOut:
    return TurnOut(
        turn_id=turn.turn_id,
        sequence=turn.sequence,
        kind=_wire(turn.kind.value),
        context=context_out(turn.context),
        occurrence_id=turn.occurrence_id,
        created_at=turn.created_at,
    )


def feedback_event_out(event: FeedbackEvent) -> FeedbackEventOut:
    return FeedbackEventOut(
        event_id=event.event_id,
        occurrence_id=event.occurrence_id,
        event_type=_wire(event.event_type.value),
        occurred_at=event.occurred_at,
        played_seconds=event.played_seconds,
        duration_seconds=event.duration_seconds,
        played_fraction=event.played_fraction,
    )


def session_detail_out(state: SessionState, history: SessionHistory, tracks: Mapping[str, Track]) -> SessionDetailOut:
    current = session_state_out(state, tracks)
    return SessionDetailOut(
        session=current.session,
        playing=current.playing,
        queue=current.queue,
        turns=[turn_out(turn) for turn in history.turns],
        occurrences=[occurrence_out(occurrence, tracks) for occurrence in history.occurrences],
        feedback_events=[feedback_event_out(event) for event in history.feedback_events],
    )


def interpretation_out(interpretation: Interpretation) -> InterpretationOut:
    return InterpretationOut(
        weight=interpretation.weight,
        basis=_wire(interpretation.basis.value),
        excluded=interpretation.excluded,
        at=interpretation.at,
        occurrence_id=interpretation.occurrence_id,
    )


def feedback_out(outcome: FeedbackOutcome, tracks: Mapping[str, Track]) -> FeedbackOut:
    return FeedbackOut(
        event=feedback_event_out(outcome.event),
        event_weight=outcome.event_weight,
        interpretation=interpretation_out(outcome.interpretation),
        state=session_state_out(outcome.state, tracks),
    )


def feedback_fact_out(outcome: FeedbackOutcome) -> FeedbackFactOut:
    return FeedbackFactOut(
        event=feedback_event_out(outcome.event),
        event_weight=outcome.event_weight,
        interpretation=interpretation_out(outcome.interpretation),
    )


# --- Typed messages and the vocabulary (B9) ---------------------------------------------


def meaning_out(meaning: MessageMeaning) -> MeaningOut:
    kind = meaning.kind
    return MeaningOut(
        kind=_wire(kind.value),
        turn=_wire(meaning.turn.value) if kind is MeaningKind.TURN else None,
        reaction=_wire(meaning.reaction.value) if kind is MeaningKind.REACTION else None,
    )


def vocabulary_out(vocabulary: Vocabulary) -> VocabularyOut:
    return VocabularyOut(
        genres=list(vocabulary.genres),
        moods=list(vocabulary.tune_moods),
        energy=[EnergyLevelOut(id=level.level_id, label=level.label, target_energy=level.target_energy) for level in ENERGY_LEVELS],
        library=LibraryReadinessOut(ready=vocabulary.capability.ready, playable_tracks=vocabulary.capability.playable_tracks),
        dimensions=DimensionsOut(**{dimension: vocabulary.capability.state(dimension).value.lower() for dimension in DIMENSIONS}),
        usable_moods=list(vocabulary.usable_tune_moods),
        unmapped_fields=list(UNMAPPED_CONTEXT_FIELDS),
    )


# --- Playlists -----------------------------------------------------------------------


def playlist_summary_out(summary: PlaylistSummary) -> PlaylistSummaryOut:
    return PlaylistSummaryOut(
        playlist_id=summary.playlist.playlist_id,
        name=summary.playlist.name,
        track_count=summary.track_count,
        created_at=summary.playlist.created_at,
        updated_at=summary.playlist.updated_at,
    )


def playlist_out(contents: PlaylistContents, tracks: Mapping[str, Track]) -> PlaylistOut:
    return PlaylistOut(
        playlist_id=contents.playlist.playlist_id,
        name=contents.playlist.name,
        created_at=contents.playlist.created_at,
        updated_at=contents.playlist.updated_at,
        items=[
            PlaylistItemOut(position=item.position, added_at=item.added_at, track=track_out(tracks[item.track_id]))
            for item in contents.items
        ],
    )


def page(items: Sequence[T], limit: int, offset: int, convert: Callable[[T], object]) -> Dict[str, object]:
    """One page of an already loaded list, converted, as {items, total, limit, offset}."""
    return {
        "items": [convert(item) for item in items[offset : offset + limit]],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }
