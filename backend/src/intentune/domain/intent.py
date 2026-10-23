"""The listening vocabulary, and what a typed message means (Prototype 1, phase B9).

Intent reaches the backend two ways (the B9 hybrid input decision):
- a control whose meaning the UI already knows (a quick action, a Tune value,
  a starter, Like, Next) arrives as a structured command and never comes here;
- only typed language is interpreted, by an IntentInterpreter
  (ports/intent.py), into a MessageMeaning. The recommendation policy never
  sees the text.

The vocabulary:
- **Energy** is a scale of five levels, each a fixed target_energy.
- **Moods offered in Tune** are the approved design's five (CURATED_MOODS).
  The interpreter also recognizes mood labels the listener's library declares.
- **Genres** are the primary genres the library's playable tracks declare:
  the ones Recommendation Policy v1 can match.

What the library can act on is computed from the library as it is now
(LibraryCapability), never configured, from candidate_from_track(): the same
projection Policy v1 ranks. Three situations are told apart:
- **No playable tracks:** the library is not ready. That is a setup state,
  not an unsupported dimension: nothing can be recommended until music is
  imported (LibraryNotReady, API code LIBRARY_NOT_READY).
- **Playable tracks, but no usable data for a dimension:** that dimension is
  unavailable for now (NO_DATA). This is unfinished feature coverage, not a
  smaller domain: Policy v1 keeps every target, and nothing is invented.
- **Playable tracks with usable data:** the dimension is usable (USABLE), by
  structured controls, typed words, and Policy v1 alike.

Each dimension becomes usable on its own as soon as some playable track
carries usable data for it: genre with a genre label, mood with any mood
label (B10 carry-forward: the dimension is the library's, so a library mood
such as "Dreamy" counts; Tune's curated choices are only the five the library
also declares, usable_tune_moods), and energy, danceability, tempo, valence,
and acousticness with a value from an approved feature pipeline. Today the importer reads genre tags
only and nothing measures the five features, so only genre can be usable.
current_mood, listening_goal, and activity are kept and stored, but their
mapping into Policy v1 is unfinished (UNMAPPED_CONTEXT_FIELDS): they change
no recommendation, and nothing here claims they do.

unavailable_dimensions() is the one rule for what an intent may ask of a
ready library, for every way intent arrives: a typed refinement, a structured
refine, or a session start. A genre or mood value is usable when some
playable track declares it, and a target when some playable track has that
feature. Only what the intent changes is checked, and clearing is always
allowed. IntentUnavailable reports what failed (API code INTENT_UNAVAILABLE):
the request was understood, but the library has no data to act on it yet.

Pure: no database, HTTP, or file code.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Sequence, Tuple

from src.intentune.domain.library import Track
from src.intentune.domain.models import ListeningContext, MusicCandidate
from src.intentune.domain.policy import candidate_from_track, requested_moods
from src.intentune.domain.session import FeedbackEventType, TurnKind


@dataclass(frozen=True)
class EnergyLevel:
    level_id: str
    label: str
    target_energy: float


ENERGY_LEVELS: Tuple[EnergyLevel, ...] = (
    EnergyLevel("very-low", "Very low", 0.1),
    EnergyLevel("low", "Low", 0.3),
    EnergyLevel("medium", "Medium", 0.5),
    EnergyLevel("high", "High", 0.7),
    EnergyLevel("very-high", "Very high", 0.9),
)
_MEDIUM = 2

CURATED_MOODS: Tuple[str, ...] = ("Emotional", "Focused", "Calm", "Joyful", "Driven")
"""The moods Tune offers: the approved design's, whatever the library's tags say."""


def energy_level(target_energy: Optional[float]) -> Optional[EnergyLevel]:
    """The level a target belongs to: the nearest one, the lower one halfway (a target set elsewhere may fall between)."""
    if target_energy is None:
        return None
    return min(ENERGY_LEVELS, key=lambda level: (round(abs(level.target_energy - target_energy), 9), level.target_energy))


def stepped_energy(target_energy: Optional[float], steps: int) -> float:
    """The target one or more levels up (+) or down (-), within the scale. With no target yet, from Medium."""
    level = energy_level(target_energy)
    index = ENERGY_LEVELS.index(level) if level is not None else _MEDIUM
    return ENERGY_LEVELS[max(0, min(len(ENERGY_LEVELS) - 1, index + steps))].target_energy


def _distinct(values: Iterable[str]) -> Tuple[str, ...]:
    """Distinct values, ignoring case and surrounding space (as Policy v1 compares labels), sorted, first casing kept."""
    seen = {}
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned.casefold() not in seen:
            seen[cleaned.casefold()] = cleaned
    return tuple(sorted(seen.values(), key=str.casefold))


DIMENSIONS: Tuple[str, ...] = ("mood", "genre", "energy", "danceability", "tempo", "valence", "acousticness")
"""Every intent dimension Policy v1 can rank by, in the order guidance names them: Tune's three first."""

# The measured dimensions: the candidate feature each is read from, and the context target that asks for it.
_MEASURED = {
    "energy": ("energy", "target_energy"),
    "danceability": ("danceability", "target_danceability"),
    "tempo": ("tempo_bpm", "target_tempo_bpm"),
    "valence": ("valence", "target_valence"),
    "acousticness": ("acousticness", "target_acousticness"),
}

UNMAPPED_CONTEXT_FIELDS: Tuple[str, ...] = ("current_mood", "listening_goal", "activity")
"""Context fields stored with a session whose mapping into Policy v1 is unfinished: they change no recommendation.

They stay in the domain. An approved deterministic mapping, or a future interpretation rule, will give them an effect.
"""


class DimensionState(str, Enum):
    USABLE = "USABLE"  # some playable track has usable data for it: asking for it changes what plays
    NO_DATA = "NO_DATA"  # tracks are playable, but none has usable data for it yet (unfinished feature coverage)
    LIBRARY_NOT_READY = "LIBRARY_NOT_READY"  # nothing is playable: a setup state, not a missing feature


@dataclass(frozen=True)
class LibraryCapability:
    """What the recommendation engine can truthfully use, with the library in its current state.

    Computed from the library, never configured: a dimension is usable while some playable track carries usable
    data for it, and only then.
    """

    playable_tracks: int = 0
    usable: Tuple[str, ...] = ()  # the dimensions with usable data, in DIMENSIONS order

    def __post_init__(self) -> None:
        unknown = set(self.usable) - set(DIMENSIONS)
        if unknown:
            raise ValueError(f"unknown intent dimensions: {sorted(unknown)}")
        if self.playable_tracks < 0:
            raise ValueError("playable_tracks cannot be negative")
        if self.usable and not self.playable_tracks:
            raise ValueError("a library with nothing playable can use no dimension")
        object.__setattr__(self, "usable", tuple(dimension for dimension in DIMENSIONS if dimension in self.usable))

    @property
    def ready(self) -> bool:
        """Whether anything can be recommended at all: some track is playable."""
        return self.playable_tracks > 0

    def uses(self, dimension: str) -> bool:
        return dimension in self.usable

    def state(self, dimension: str) -> DimensionState:
        if dimension not in DIMENSIONS:
            raise ValueError(f"unknown intent dimension: {dimension}")
        if not self.ready:
            return DimensionState.LIBRARY_NOT_READY
        return DimensionState.USABLE if self.uses(dimension) else DimensionState.NO_DATA


@dataclass(frozen=True)
class Vocabulary:
    """The words intent is expressed in, and which of them the library can act on.

    genres and library_moods are what the library's playable tracks declare,
    as Policy v1 reads them (their primary labels).
    """

    genres: Tuple[str, ...] = ()
    library_moods: Tuple[str, ...] = ()
    capability: LibraryCapability = LibraryCapability()

    def mood_is_usable(self, mood: str) -> bool:
        """True when some playable track declares this mood, so asking for it can change what plays."""
        return _key(mood) in {_key(usable) for usable in self.library_moods}

    def genre_is_usable(self, genre: str) -> bool:
        """True when some playable track declares this genre, so asking for it can change what plays."""
        return _key(genre) in {_key(usable) for usable in self.genres}

    @property
    def usable_tune_moods(self) -> Tuple[str, ...]:
        """Tune's moods that some playable track declares, in Tune's order: the ones worth offering as choices."""
        return tuple(mood for mood in CURATED_MOODS if self.mood_is_usable(mood))

    @property
    def tune_moods(self) -> Tuple[str, ...]:
        return CURATED_MOODS

    @property
    def moods(self) -> Tuple[str, ...]:
        """Every mood a typed message may name: the curated ones and the library's."""
        return _distinct(CURATED_MOODS + self.library_moods)


def _key(label: str) -> str:
    """A label as Policy v1 compares it: ignoring case and surrounding space."""
    return label.strip().casefold()


def vocabulary_from_candidates(playable: Sequence[MusicCandidate]) -> Vocabulary:
    """The vocabulary and capability of a library, from the candidates Policy v1 ranks: one per playable track.

    A dimension is usable as soon as some candidate carries usable data for it, so a feature pipeline that starts
    filling a value makes its dimension usable with no change here.
    """
    genres = _distinct(music.genre for music in playable if music.genre)
    moods = _distinct(music.mood for music in playable if music.mood)
    usable = []
    if moods:  # any real mood label: the dimension is the library's, not Tune's five (usable_tune_moods)
        usable.append("mood")
    if genres:
        usable.append("genre")
    usable.extend(
        dimension for dimension, (feature, _) in _MEASURED.items() if any(getattr(music, feature) is not None for music in playable)
    )
    return Vocabulary(genres=genres, library_moods=moods, capability=LibraryCapability(len(playable), tuple(usable)))


def vocabulary_from_tracks(tracks: Iterable[Track]) -> Vocabulary:
    """The vocabulary and capability of a library, from what Policy v1 can use of each playable track."""
    return vocabulary_from_candidates([candidate.music for candidate in map(candidate_from_track, tracks) if candidate.available])


# --- What the library can act on ---------------------------------------------------------------


def unavailable_dimensions(before: ListeningContext, after: ListeningContext, vocabulary: Vocabulary) -> Tuple[str, ...]:
    """The dimensions an intent changes to something the library has no usable data for, in DIMENSIONS order.

    before is the intent in force (empty for a new session); after, the one asked for. Ask it of a ready library:
    with nothing playable, the answer is LibraryNotReady, not a list of dimensions.
    """
    unavailable = []
    moods = requested_moods(after)
    if moods != requested_moods(before) and not all(vocabulary.mood_is_usable(mood) for mood in moods):
        unavailable.append("mood")
    genres = after.temporary_genres
    if genres != before.temporary_genres and not all(vocabulary.genre_is_usable(genre) for genre in genres):
        unavailable.append("genre")
    for dimension, (_, target) in _MEASURED.items():
        asked = getattr(after, target)
        if asked is not None and asked != getattr(before, target) and not vocabulary.capability.uses(dimension):
            unavailable.append(dimension)
    return tuple(unavailable)


class LibraryNotReady(ValueError):
    """Nothing in the library is playable (API code LIBRARY_NOT_READY). Nothing was started or recorded.

    A setup state, not an unsupported intent: music must be imported before anything can be recommended.
    """

    def __init__(self) -> None:
        super().__init__("the library has no playable tracks")


class IntentUnavailable(ValueError):
    """The library cannot act on part of an intent (API code INTENT_UNAVAILABLE). Nothing was changed or recorded.

    The intent was understood, and the library is ready, but it has no usable data for this yet; asking for it
    would change nothing that plays.
    """

    def __init__(self, unavailable: Tuple[str, ...], supported: Tuple[str, ...]) -> None:
        super().__init__(", ".join(unavailable))
        self.unavailable = tuple(unavailable)  # what was asked for that the library cannot use
        self.supported = tuple(supported)  # the dimensions the library can use: what is worth asking instead


# --- What a typed message means ----------------------------------------------------------------


class MeaningKind(str, Enum):
    REFINE = "REFINE"  # a new listening context
    TURN = "TURN"  # a steering turn: a control, NEXT, or NOT_FOR_ME
    REACTION = "REACTION"  # LIKE or REPLAY, about the recommendation in view
    SAVE_REQUESTED = "SAVE_REQUESTED"  # the listener wants to save it; the UI asks where


class NotUnderstoodReason(str, Enum):
    UNRECOGNIZED = "UNRECOGNIZED"  # nothing in the message is in the vocabulary
    AMBIGUOUS = "AMBIGUOUS"  # it asks for more than one thing at once, or for opposite things
    UNSUPPORTED = "UNSUPPORTED"  # it asks for something that cannot be expressed, such as excluding a genre
    NO_RECOMMENDATION = "NO_RECOMMENDATION"  # it is about a recommendation, and there is none yet


MESSAGE_TURNS = frozenset(
    {
        TurnKind.SURPRISE_ME,
        TurnKind.MORE_FAMILIAR,
        TurnKind.MORE_LIKE_THIS,
        TurnKind.TRY_SOMETHING_DIFFERENT,
        TurnKind.NEXT,
        TurnKind.NOT_FOR_ME,
    }
)
MESSAGE_REACTIONS = frozenset({FeedbackEventType.LIKE, FeedbackEventType.REPLAY})


@dataclass(frozen=True)
class MessageMeaning:
    """What a typed message means: exactly one structured meaning, or the reason it has none.

    The text itself is not kept (D33).
    """

    kind: Optional[MeaningKind] = None
    context: Optional[ListeningContext] = None
    turn: Optional[TurnKind] = None
    reaction: Optional[FeedbackEventType] = None
    not_understood: Optional[NotUnderstoodReason] = None

    def __post_init__(self) -> None:
        if self.not_understood is not None:
            object.__setattr__(self, "not_understood", NotUnderstoodReason(self.not_understood))
            if (self.kind, self.context, self.turn, self.reaction) != (None, None, None, None):
                raise ValueError("a message that is not understood has no meaning")
            return
        kind = MeaningKind(self.kind)
        object.__setattr__(self, "kind", kind)
        if (kind is MeaningKind.REFINE) != (self.context is not None):
            raise ValueError("a REFINE meaning carries the new context, and only it does")
        if (kind is MeaningKind.TURN) != (self.turn is not None) or (self.turn is not None and TurnKind(self.turn) not in MESSAGE_TURNS):
            raise ValueError("a TURN meaning carries one of the steering turns a message can ask for")
        if (kind is MeaningKind.REACTION) != (self.reaction is not None) or (
            self.reaction is not None and FeedbackEventType(self.reaction) not in MESSAGE_REACTIONS
        ):
            raise ValueError("a REACTION meaning carries LIKE or REPLAY")

    @property
    def understood(self) -> bool:
        return self.not_understood is None

    @classmethod
    def refine(cls, context: ListeningContext) -> "MessageMeaning":
        return cls(kind=MeaningKind.REFINE, context=context)

    @classmethod
    def steering(cls, turn: TurnKind) -> "MessageMeaning":
        return cls(kind=MeaningKind.TURN, turn=turn)

    @classmethod
    def reacting(cls, reaction: FeedbackEventType) -> "MessageMeaning":
        return cls(kind=MeaningKind.REACTION, reaction=reaction)

    @classmethod
    def save_requested(cls) -> "MessageMeaning":
        return cls(kind=MeaningKind.SAVE_REQUESTED)

    @classmethod
    def not_understood_because(cls, reason: NotUnderstoodReason) -> "MessageMeaning":
        return cls(not_understood=reason)


class MessageNotUnderstood(ValueError):
    """Intentune cannot act on a typed message (API code MESSAGE_NOT_UNDERSTOOD). Nothing was changed or recorded."""

    def __init__(self, reason: NotUnderstoodReason, supported: Tuple[str, ...] = ("mood", "genre", "energy")) -> None:
        super().__init__(reason.value)
        self.reason = NotUnderstoodReason(reason)
        self.supported = tuple(supported)  # the dimensions the library can use: what is worth asking instead
