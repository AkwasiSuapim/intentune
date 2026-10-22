"""Request and response bodies of the HTTP API (B8), separate from domain and ORM models.

Requests are strict: unknown fields are rejected, numbers must be JSON numbers
(not strings or booleans) and finite, and text has a length limit:

- context labels (moods, goal, activity, genres, moods): 1 to 100 characters
  after trimming, at most 20 genres and 20 moods;
- playlist names: the domain's limit (MAX_PLAYLIST_NAME_LENGTH);
- ids: at most 64 characters (an id of nothing is a not-found error);
- a typed message: 1 to 500 characters after trimming (B9). It is interpreted,
  then dropped, never stored (D33);
- a folder path to register: at most 4096 characters.

Enumerations travel in lowercase (`not_for_me`, `queued`), in snake_case as
the spec's turn variants do. Times are ISO 8601 in UTC.

No response carries a filesystem path. A track's audio is addressed by
audio_url, which names its id.
"""

from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.intentune.domain.models import ListeningContext
from src.intentune.domain.playlist import MAX_PLAYLIST_NAME_LENGTH

MAX_LABEL_LENGTH = 100
MAX_LABELS = 20
MAX_ID_LENGTH = 64
MAX_PATH_LENGTH = 4096
MAX_MESSAGE_LENGTH = 500
MAX_PLAYLIST_ORDER = 10_000
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_LABEL_LENGTH)]
Labels = Annotated[List[Label], Field(max_length=MAX_LABELS)]
Unit = Annotated[float, Field(ge=0.0, le=1.0, strict=True, allow_inf_nan=False)]
Tempo = Annotated[float, Field(gt=0.0, strict=True, allow_inf_nan=False)]
Seconds = Annotated[float, Field(ge=0.0, strict=True, allow_inf_nan=False)]
Duration = Annotated[float, Field(gt=0.0, strict=True, allow_inf_nan=False)]
Id = Annotated[str, StringConstraints(min_length=1, max_length=MAX_ID_LENGTH)]
PlaylistName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_PLAYLIST_NAME_LENGTH)]
MessageText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_LENGTH)]

TurnKindName = Literal[
    "initial_intent",
    "refine",
    "next",
    "not_for_me",
    "more_like_this",
    "surprise_me",
    "more_familiar",
    "try_something_different",
    "message",
]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Requests ----------------------------------------------------------------------------


class ContextIn(_Request):
    """A structured ListeningContext (D29). Every field is optional; nothing absent is filled in."""

    current_mood: Optional[Label] = None
    desired_mood: Optional[Label] = None
    listening_goal: Optional[Label] = None
    activity: Optional[Label] = None
    temporary_genres: Labels = []
    temporary_moods: Labels = []
    target_energy: Optional[Unit] = None
    target_danceability: Optional[Unit] = None
    target_valence: Optional[Unit] = None
    target_acousticness: Optional[Unit] = None
    target_tempo_bpm: Optional[Tempo] = None

    def to_domain(self) -> ListeningContext:
        return ListeningContext(**self.model_dump())


class PlaybackIn(_Request):
    """How far the player got through the track that is ending, as it measured (B9)."""

    played_seconds: Seconds
    duration_seconds: Duration


class StartSessionIn(_Request):
    """Start from a structured context (a starter, Tune), or from the listener's typed words (B9). Exactly one."""

    context: Optional[ContextIn] = None
    message: Optional[MessageText] = None

    @model_validator(mode="after")
    def _one_way_to_start(self) -> "StartSessionIn":
        if (self.context is None) == (self.message is None):
            raise ValueError("A session starts from a context or from a message, exactly one of them.")
        return self


class TurnIn(_Request):
    """A steering turn. refine carries the new context; not_for_me and more_like_this may name an occurrence.

    B9:
    - next may carry the player's facts about the track it ends (playback), so
      the skip is recorded as evidence.
    - message carries typed text, interpreted by the backend. occurrence_id is
      then the recommendation in view ("this"), and playback is the player's
      facts, used if the message means next.
    """

    kind: TurnKindName
    context: Optional[ContextIn] = None
    occurrence_id: Optional[Id] = None
    text: Optional[MessageText] = None
    playback: Optional[PlaybackIn] = None

    @model_validator(mode="after")
    def _fields_fit_the_kind(self) -> "TurnIn":
        if (self.kind == "message") != (self.text is not None):
            raise ValueError("A message turn carries text, and only a message turn does.")
        if self.context is not None and self.kind != "refine":
            raise ValueError("A REFINE turn carries the new context, and only a REFINE turn does.")
        if self.playback is not None and self.kind not in ("next", "message"):
            raise ValueError("Only next and message turns carry playback facts.")
        return self


class PlaybackEventIn(_Request):
    """How an occurrence's playback ended, as the player measured it (spec §22: no progress ticks)."""

    occurrence_id: Id
    event_type: Literal["skip", "complete"]
    played_seconds: Seconds
    duration_seconds: Duration


class ReactionIn(_Request):
    """unlike (B9) takes back a Like: the Like stays recorded, and no longer counts as evidence."""

    reaction: Literal["like", "unlike", "save", "replay", "not_for_me"]


class RegisterSourceIn(_Request):
    path: Annotated[str, StringConstraints(min_length=1, max_length=MAX_PATH_LENGTH)]


class ImportIn(_Request):
    source_id: Id


class PlaylistNameIn(_Request):
    name: PlaylistName


class AddPlaylistItemIn(_Request):
    """A library track. session_id and occurrence_id, together, say it is a recommendation of that session."""

    track_id: Id
    session_id: Optional[Id] = None
    occurrence_id: Optional[Id] = None


class PlaylistOrderIn(_Request):
    track_ids: Annotated[List[Id], Field(max_length=MAX_PLAYLIST_ORDER)]


# --- Responses ---------------------------------------------------------------------------


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"


class TrackOut(BaseModel):
    track_id: str
    title: Optional[str]
    file_name: str  # the source file's name, never its folder
    artist: Optional[str]
    album: Optional[str]
    year: Optional[int]
    duration_seconds: Optional[float]
    format: str
    status: str
    playable: bool
    genres: List[str]
    moods: List[str]
    audio_url: str


class TrackPageOut(BaseModel):
    items: List[TrackOut]
    total: int
    limit: int
    offset: int


class SourceOut(BaseModel):
    source_id: str
    name: str  # the folder's own name; the full path is never returned
    status: str
    created_at: datetime
    last_scanned_at: Optional[datetime]


class SourceListOut(BaseModel):
    items: List[SourceOut]
    scanning: bool


class ScanReportOut(BaseModel):
    source_id: str
    source_missing: bool
    imported: int
    duplicates: int
    unchanged: int
    repaired: int
    unsupported: int
    failed: int
    missing: int
    ignored: int
    tag_failures: int


class ScanReportsOut(BaseModel):
    reports: List[ScanReportOut]


class JobOut(BaseModel):
    job_id: str
    track_id: str
    kind: str
    analyzer: str
    status: str
    attempts: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    failure_reason: Optional[str]
    error_message: Optional[str]


class JobPageOut(BaseModel):
    items: List[JobOut]
    total: int
    limit: int
    offset: int


class ContextOut(BaseModel):
    current_mood: Optional[str]
    desired_mood: Optional[str]
    listening_goal: Optional[str]
    activity: Optional[str]
    temporary_genres: List[str]
    temporary_moods: List[str]
    target_energy: Optional[float]
    target_danceability: Optional[float]
    target_valence: Optional[float]
    target_acousticness: Optional[float]
    target_tempo_bpm: Optional[float]


class SessionOut(BaseModel):
    session_id: str
    status: str
    context: ContextOut
    started_at: datetime
    updated_at: datetime
    ended_at: Optional[datetime]
    end_reason: Optional[str]


class SessionPageOut(BaseModel):
    items: List[SessionOut]
    total: int
    limit: int
    offset: int


class OccurrenceOut(BaseModel):
    """A recommendation surfaced in the session, with its track."""

    occurrence_id: str
    track: TrackOut
    status: str
    rank: int
    score: Optional[float]
    algorithm: str
    is_exploration: bool
    surfaced_position: int
    queue_position: Optional[int]
    surfaced_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class SessionStateOut(BaseModel):
    session: SessionOut
    playing: Optional[OccurrenceOut]
    queue: List[OccurrenceOut]


class TurnOut(BaseModel):
    turn_id: str
    sequence: int
    kind: str
    context: ContextOut
    occurrence_id: Optional[str]
    created_at: datetime


class FeedbackEventOut(BaseModel):
    event_id: str
    occurrence_id: str
    event_type: str
    occurred_at: datetime
    played_seconds: Optional[float]
    duration_seconds: Optional[float]
    played_fraction: Optional[float]


class SessionDetailOut(SessionStateOut):
    """The session now, and how it got here: every turn, occurrence, and feedback event, oldest first."""

    turns: List[TurnOut]
    occurrences: List[OccurrenceOut]
    feedback_events: List[FeedbackEventOut]


class MeaningOut(BaseModel):
    """What a typed message was understood as (B9): a refinement, a steering turn, a reaction, or a save request."""

    kind: Literal["refine", "turn", "reaction", "save_requested"]
    turn: Optional[str] = None
    reaction: Optional[str] = None


class EnergyLevelOut(BaseModel):
    id: str
    label: str
    target_energy: float


class LibraryReadinessOut(BaseModel):
    """Whether anything can be recommended: a library with no playable tracks is not ready (a setup state)."""

    ready: bool
    playable_tracks: int


DimensionStateName = Literal["usable", "no_data", "library_not_ready"]


class DimensionsOut(BaseModel):
    """What each intent dimension's data allows, with the library as it is now.

    usable: some playable track has usable data for it. no_data: tracks are playable, but none has usable data
    for it yet. library_not_ready: nothing is playable, so no dimension can be judged.
    """

    mood: DimensionStateName
    genre: DimensionStateName
    energy: DimensionStateName
    danceability: DimensionStateName
    tempo: DimensionStateName
    valence: DimensionStateName
    acousticness: DimensionStateName


class VocabularyOut(BaseModel):
    """What Tune offers (B9): the library's genres, the curated moods, the energy scale, and what the library can act on now."""

    genres: List[str]
    moods: List[str]
    energy: List[EnergyLevelOut]
    library: LibraryReadinessOut
    dimensions: DimensionsOut
    usable_moods: List[str]  # the curated moods some playable track declares; choosing another changes nothing
    unmapped_fields: List[str]  # context fields that are stored but not yet mapped into Policy v1


class InterpretationOut(BaseModel):
    """What everything about the track in this session now means (Feedback Policy v1)."""

    weight: float
    basis: str
    excluded: bool
    at: Optional[datetime]
    occurrence_id: Optional[str]


class FeedbackOut(BaseModel):
    event: FeedbackEventOut
    event_weight: float
    interpretation: InterpretationOut
    state: SessionStateOut


class FeedbackFactOut(BaseModel):
    """The feedback a typed message recorded (B9); the session after it is the result's state."""

    event: FeedbackEventOut
    event_weight: float
    interpretation: InterpretationOut


class TurnResultOut(BaseModel):
    """The turn recorded and the session after the re-rank.

    For a typed message (B9), meaning says what it was understood as. A message
    that was a reaction records feedback instead of a turn, and a save request
    records neither.
    """

    meaning: Optional[MeaningOut] = None
    turn: Optional[TurnOut] = None
    feedback: Optional[FeedbackFactOut] = None
    state: SessionStateOut


class SessionStartOut(SessionStateOut):
    """A started session. Started from a message (B9), meaning says how it was read, and turn is the control it applied."""

    meaning: Optional[MeaningOut] = None
    turn: Optional[TurnOut] = None


class PlaylistSummaryOut(BaseModel):
    playlist_id: str
    name: str
    track_count: int
    created_at: datetime
    updated_at: datetime


class PlaylistListOut(BaseModel):
    items: List[PlaylistSummaryOut]


class PlaylistItemOut(BaseModel):
    position: int
    added_at: datetime
    track: TrackOut


class PlaylistOut(BaseModel):
    playlist_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    items: List[PlaylistItemOut]


class PlaylistItemAddedOut(BaseModel):
    playlist: PlaylistOut
    feedback: Optional[FeedbackOut]


class ErrorBodyOut(BaseModel):
    code: str
    message: str
    details: dict
    request_id: str


class ErrorOut(BaseModel):
    """The error envelope (spec §26), for the OpenAPI document."""

    error: ErrorBodyOut
