"""Canonical, source-independent domain models for Intentune's recommendation engine.

These types describe music candidates, listener preferences, session intent,
feature importance, and scoring results without depending on any particular
data source (CSV, database, YouTube, Spotify) or delivery framework (FastAPI,
Streamlit, HTTP, an ORM). See docs/architecture/architecture.md for the full boundary rules
and docs/decisions/technical-decisions.md for the decision record behind this module.

This milestone only introduces the models and their validation. Nothing here
changes the existing scoring algorithm in src/recommender.py.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple, Union

Number = Union[int, float]

_SCORE_TOLERANCE = 1e-6


def _require_text(value: object, field_name: str) -> str:
    """Validate a required string: must be a string and non-blank after trimming."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be blank")
    return cleaned


def _optional_text(value: Optional[str], field_name: str) -> Optional[str]:
    """Validate an optional string: None is allowed, but a provided value must be non-blank."""
    if value is None:
        return None
    return _require_text(value, field_name)


def _require_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    return float(value)


def _validate_unit_range(value: Optional[Number], field_name: str) -> Optional[float]:
    """Validate an optional 0.0-1.0 feature value. None means the value is simply unknown."""
    if value is None:
        return None
    numeric_value = _require_number(value, field_name)
    if not 0.0 <= numeric_value <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")
    return numeric_value


def _validate_positive_tempo(value: Optional[Number], field_name: str) -> Optional[float]:
    """Validate an optional tempo value: None is allowed, but a provided tempo must be positive."""
    if value is None:
        return None
    numeric_value = _require_number(value, field_name)
    if numeric_value <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    return numeric_value


def _normalize_text_collection(values: object, field_name: str) -> Tuple[str, ...]:
    """Trim whitespace, reject blank entries, and drop case-insensitive duplicates.

    The first-seen casing of each distinct value is preserved.
    """
    if values is None:
        return ()
    if isinstance(values, str) or not isinstance(values, (list, tuple, set, frozenset)):
        raise ValueError(f"{field_name} must be a list of strings")

    normalized: list = []
    seen = set()
    for raw_value in values:
        cleaned = _require_text(raw_value, field_name)
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            normalized.append(cleaned)
    return tuple(normalized)


@dataclass
class MusicCandidate:
    """A single item Intentune's recommendation domain can rank.

    A candidate may represent a row from the current CSV baseline, a future
    database song, a future YouTube video, a future Spotify track, or another
    provider's music result. Audio-feature fields are optional because
    external providers -- starting with YouTube -- cannot reliably supply
    genre, mood, energy, danceability, tempo, valence, or acousticness.

    This model intentionally has no knowledge of CSV columns, HTTP, or any
    provider's API response shape.
    """

    candidate_id: str
    title: str
    creator: str
    source: str
    genre: Optional[str] = None
    mood: Optional[str] = None
    energy: Optional[float] = None
    danceability: Optional[float] = None
    tempo_bpm: Optional[float] = None
    valence: Optional[float] = None
    acousticness: Optional[float] = None
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None

    def __post_init__(self) -> None:
        self.candidate_id = _require_text(self.candidate_id, "candidate_id")
        self.title = _require_text(self.title, "title")
        self.creator = _require_text(self.creator, "creator")
        self.source = _require_text(self.source, "source")
        self.genre = _optional_text(self.genre, "genre")
        self.mood = _optional_text(self.mood, "mood")
        self.energy = _validate_unit_range(self.energy, "energy")
        self.danceability = _validate_unit_range(self.danceability, "danceability")
        self.valence = _validate_unit_range(self.valence, "valence")
        self.acousticness = _validate_unit_range(self.acousticness, "acousticness")
        self.tempo_bpm = _validate_positive_tempo(self.tempo_bpm, "tempo_bpm")
        self.url = _optional_text(self.url, "url")
        self.thumbnail_url = _optional_text(self.thumbnail_url, "thumbnail_url")


@dataclass
class UserProfile:
    """A listener's longer-term music taste, independent of any single session.

    Every preference is optional: a user is not required to specify every
    field, and a missing preference must not be replaced with an invented
    default anywhere in the domain -- that decision is left to the future
    scoring engine (see docs/planning/development-phases.md).
    """

    preferred_genres: Tuple[str, ...] = field(default_factory=tuple)
    preferred_moods: Tuple[str, ...] = field(default_factory=tuple)
    preferred_energy: Optional[float] = None
    preferred_danceability: Optional[float] = None
    preferred_tempo_bpm: Optional[float] = None
    preferred_valence: Optional[float] = None
    preferred_acousticness: Optional[float] = None

    def __post_init__(self) -> None:
        self.preferred_genres = _normalize_text_collection(self.preferred_genres, "preferred_genres")
        self.preferred_moods = _normalize_text_collection(self.preferred_moods, "preferred_moods")
        self.preferred_energy = _validate_unit_range(self.preferred_energy, "preferred_energy")
        self.preferred_danceability = _validate_unit_range(self.preferred_danceability, "preferred_danceability")
        self.preferred_valence = _validate_unit_range(self.preferred_valence, "preferred_valence")
        self.preferred_acousticness = _validate_unit_range(self.preferred_acousticness, "preferred_acousticness")
        self.preferred_tempo_bpm = _validate_positive_tempo(self.preferred_tempo_bpm, "preferred_tempo_bpm")


@dataclass
class ListeningContext:
    """What a listener wants right now, distinct from their long-term UserProfile.

    A manual form, a future FastAPI request, a saved session, or an AI
    chatbot may construct this model later. This milestone only defines the
    shape and validation -- it does not interpret mood, infer intent, or
    apply any context presets.

    Prototype 1 (B5, B9): Recommendation Policy v1 reads temporary_genres,
    temporary_moods (or desired_mood when there are none), and the five
    targets. current_mood, listening_goal, and activity are kept and stored,
    but their mapping into Policy v1 is unfinished: they change no
    recommendation yet (domain/intent.py, UNMAPPED_CONTEXT_FIELDS).
    """

    current_mood: Optional[str] = None
    desired_mood: Optional[str] = None
    listening_goal: Optional[str] = None
    activity: Optional[str] = None
    temporary_genres: Tuple[str, ...] = field(default_factory=tuple)
    temporary_moods: Tuple[str, ...] = field(default_factory=tuple)
    target_energy: Optional[float] = None
    target_danceability: Optional[float] = None
    target_tempo_bpm: Optional[float] = None
    target_valence: Optional[float] = None
    target_acousticness: Optional[float] = None

    def __post_init__(self) -> None:
        self.current_mood = _optional_text(self.current_mood, "current_mood")
        self.desired_mood = _optional_text(self.desired_mood, "desired_mood")
        self.listening_goal = _optional_text(self.listening_goal, "listening_goal")
        self.activity = _optional_text(self.activity, "activity")
        self.temporary_genres = _normalize_text_collection(self.temporary_genres, "temporary_genres")
        self.temporary_moods = _normalize_text_collection(self.temporary_moods, "temporary_moods")
        self.target_energy = _validate_unit_range(self.target_energy, "target_energy")
        self.target_danceability = _validate_unit_range(self.target_danceability, "target_danceability")
        self.target_valence = _validate_unit_range(self.target_valence, "target_valence")
        self.target_acousticness = _validate_unit_range(self.target_acousticness, "target_acousticness")
        self.target_tempo_bpm = _validate_positive_tempo(self.target_tempo_bpm, "target_tempo_bpm")


_FEATURE_WEIGHT_NAMES = ("genre", "mood", "energy", "danceability", "tempo", "valence", "acousticness")


@dataclass
class FeatureWeights:
    """How strongly each feature should influence one recommendation session.

    A preference or target says what value is wanted (see UserProfile and
    ListeningContext); a weight says how much that feature should matter when
    ranking. Weights are independent of any single permanent global scheme --
    a future session may combine default weights, long-term preferences,
    context, and explicit overrides into a session-specific set of weights.

    This milestone does not use FeatureWeights to change scoring yet.
    """

    genre: float = 0.0
    mood: float = 0.0
    energy: float = 0.0
    danceability: float = 0.0
    tempo: float = 0.0
    valence: float = 0.0
    acousticness: float = 0.0

    def __post_init__(self) -> None:
        for feature_name in _FEATURE_WEIGHT_NAMES:
            value = _require_number(getattr(self, feature_name), f"{feature_name} weight")
            if value < 0.0:
                raise ValueError(f"{feature_name} weight must not be negative")
            setattr(self, feature_name, value)

    @property
    def total_active_weight(self) -> float:
        """The sum of all feature weights currently assigned to this session."""
        return sum(getattr(self, feature_name) for feature_name in _FEATURE_WEIGHT_NAMES)


@dataclass
class ScoreComponent:
    """One feature's contribution to a candidate's overall score.

    Supports explainable recommendations: each component carries the points
    it earned, the points it could have earned, and a human-readable reason.
    """

    feature_name: str
    points_earned: float
    maximum_points: float
    reason: str

    def __post_init__(self) -> None:
        self.feature_name = _require_text(self.feature_name, "feature_name")
        self.reason = _require_text(self.reason, "reason")
        self.points_earned = _require_number(self.points_earned, "points_earned")
        self.maximum_points = _require_number(self.maximum_points, "maximum_points")
        if self.points_earned < 0.0:
            raise ValueError("points_earned must not be negative")
        if self.maximum_points < 0.0:
            raise ValueError("maximum_points must not be negative")
        if self.points_earned > self.maximum_points:
            raise ValueError("points_earned must not exceed maximum_points")


@dataclass
class ScoreBreakdown:
    """The complete scoring result for one candidate.

    total_score and maximum_score must agree with the sum of the component
    points and maximums, within a small floating-point tolerance. The
    existing dictionary-based public API may keep returning its historical
    (score, reasons) shape for compatibility -- this model does not replace
    that shape, it gives the domain a typed equivalent to grow into.
    """

    total_score: float
    maximum_score: float
    components: Tuple[ScoreComponent, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if isinstance(self.components, ScoreComponent) or not isinstance(self.components, (list, tuple)):
            raise ValueError("components must be a list or tuple of ScoreComponent")
        for component in self.components:
            if not isinstance(component, ScoreComponent):
                raise ValueError("components must contain only ScoreComponent instances")
        self.components = tuple(self.components)

        self.total_score = _require_number(self.total_score, "total_score")
        self.maximum_score = _require_number(self.maximum_score, "maximum_score")
        if self.total_score < 0.0:
            raise ValueError("total_score must not be negative")
        if self.maximum_score < 0.0:
            raise ValueError("maximum_score must not be negative")
        if self.total_score > self.maximum_score:
            raise ValueError("total_score must not exceed maximum_score")

        component_total = sum(component.points_earned for component in self.components)
        component_maximum = sum(component.maximum_points for component in self.components)
        if abs(component_total - self.total_score) > _SCORE_TOLERANCE:
            raise ValueError("total_score must equal the sum of the components' points_earned")
        if abs(component_maximum - self.maximum_score) > _SCORE_TOLERANCE:
            raise ValueError("maximum_score must equal the sum of the components' maximum_points")

    @property
    def normalized_score(self) -> Optional[float]:
        """total_score expressed as a 0.0-1.0 fraction of maximum_score.

        Returns None when maximum_score is 0.0, since a percentage would be
        undefined rather than a meaningful confidence value.
        """
        if self.maximum_score <= 0.0:
            return None
        return self.total_score / self.maximum_score


@dataclass
class Recommendation:
    """One ranked recommendation: a candidate paired with its score breakdown.

    rank is optional because a Recommendation may be constructed before
    ranking has occurred; once assigned, a rank must be a positive integer.
    """

    candidate: MusicCandidate
    score_breakdown: ScoreBreakdown
    rank: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, MusicCandidate):
            raise ValueError("candidate must be a MusicCandidate")
        if not isinstance(self.score_breakdown, ScoreBreakdown):
            raise ValueError("score_breakdown must be a ScoreBreakdown")
        if self.rank is not None:
            if isinstance(self.rank, bool) or not isinstance(self.rank, int):
                raise ValueError("rank must be an integer")
            if self.rank <= 0:
                raise ValueError("rank must be a positive integer")
