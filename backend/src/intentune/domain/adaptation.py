"""Long-Term Adaptation Policy v1 (Prototype 1, phase B10): conservative listener taste, traced to evidence.

The listener's long-term profile is a pure function of their persisted history:

    sessions, turns, occurrences, and raw feedback events
    + the features of the tracks they were about (candidate_from_track)
    + AdaptationPolicy (versioned, every constant in one place)
            |
            v
    derived profile, and the adjustments that lead to it from the stored one

Nothing is learned anywhere else, and nothing is stored that the history
cannot reproduce. Raw history stays authoritative: it is never changed or
marked "used".

Evidence (spec §23, D06, D10-D12):

- Each session's history is read through Feedback Policy v1, per track, by
  the same function session fit uses (policy.interpretations_by_track): one
  effective item per track per session, with explicit actions taking
  precedence over playback and an Unlike cancelling the Likes before it. A Like
  and three playlist adds of one track in one session are one item, and so is
  a run of Replays.
- An item is strong when its deciding signal is explicit at full strength
  (Like, Save, Playlist add, Replay: +1.00; Not for me: -1.00) or a 90-100%
  completion (+0.80). Skips, partial plays, and grace-period plays are never
  strong. An Unlike is never negative: it only removes a Like.
- More like this is a session-steering instruction, not a statement of taste:
  it stays strong session evidence in Policy v1, but long-term evidence is read
  without it (AdaptationPolicy.session_only_turns). A Like followed by More
  like this is one long-term item, from the Like.
- A feature a track does not have contributes nothing to that feature (D21).
  A liked genre-only track is genre evidence and nothing else.

The gate: a change needs at least min_strong_signals consistent strong items
from at least min_sessions sessions, about at least min_distinct_tracks
distinct tracks. One favourite song, however often it is liked, never makes
its genre, mood, or any measured feature a preference by itself; its raw
evidence stays stored.

- Genre and mood (categorical): items are grouped by the track's value,
  compared as Policy v1 compares labels. A value is preferred when its
  positive items outnumber its negative ones by min_strong_signals and the
  positive ones come from min_sessions sessions and min_distinct_tracks
  tracks. Two Afrobeats and two Jazz
  items are not four of anything. At most max_preferred_values values are kept
  per dimension, the best supported. The profile cannot express an aversion,
  so negative items only offset positive ones.
- Energy, danceability, tempo, valence, acousticness (numeric): items are read
  in time order. A batch is the latest run of items of one polarity whose
  values lie within the coherence span; it is consumed once it meets the gate
  (enough items, sessions, and distinct tracks), and never counted again. The first positive batch establishes the
  preference at the batch median; each later batch moves it at most one step,
  toward the median of a positive batch or away from that of a negative one.
  A negative batch cannot establish a preference: rejections alone do not say
  where to go.

Recomputation: derive_profile() always starts from an empty profile and the
whole history, so the same history gives the same profile, a cancelled piece
of evidence takes its effect with it, and old evidence never drifts the
profile further. plan_adjustments() compares the stored profile with the
derivation and returns the changes to record: one per value added or removed,
one per numeric batch since the stored value, or one RECOMPUTED change when
withdrawn evidence put the stored value off the new derivation's path.

Every constant is a Prototype 1 heuristic, to be evaluated in B11. Changing
any of them changes the version.

Pure: no database or I/O.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from statistics import median
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple, Union

from src.intentune.domain.library import Track
from src.intentune.domain.models import MusicCandidate, UserProfile
from src.intentune.domain.policy import (
    POLICY_V1,
    EvidenceBasis,
    Interpretation,
    RecommendationPolicy,
    candidate_from_track,
    interpretations_by_track,
)
from src.intentune.domain.session import SessionHistory, TurnKind
from src.intentune.domain.validation import require_canonical_uuid, require_text, require_utc_datetime


class ProfileDimension(str, Enum):
    GENRE = "GENRE"
    MOOD = "MOOD"
    ENERGY = "ENERGY"
    DANCEABILITY = "DANCEABILITY"
    TEMPO = "TEMPO"
    VALENCE = "VALENCE"
    ACOUSTICNESS = "ACOUSTICNESS"


# Each dimension: the candidate feature it is read from, and the UserProfile field it sets.
_CATEGORICAL: Dict[ProfileDimension, Tuple[str, str]] = {
    ProfileDimension.GENRE: ("genre", "preferred_genres"),
    ProfileDimension.MOOD: ("mood", "preferred_moods"),
}
_NUMERIC: Dict[ProfileDimension, Tuple[str, str]] = {
    ProfileDimension.ENERGY: ("energy", "preferred_energy"),
    ProfileDimension.DANCEABILITY: ("danceability", "preferred_danceability"),
    ProfileDimension.TEMPO: ("tempo_bpm", "preferred_tempo_bpm"),
    ProfileDimension.VALENCE: ("valence", "preferred_valence"),
    ProfileDimension.ACOUSTICNESS: ("acousticness", "preferred_acousticness"),
}
CATEGORICAL_DIMENSIONS = tuple(_CATEGORICAL)
NUMERIC_DIMENSIONS = tuple(_NUMERIC)


class AdjustmentChange(str, Enum):
    ADDED = "ADDED"  # a genre or mood joined the profile
    REMOVED = "REMOVED"  # a genre or mood left it
    SET = "SET"  # a numeric preference was established
    RAISED = "RAISED"
    LOWERED = "LOWERED"
    CLEARED = "CLEARED"  # a numeric preference no longer has the evidence that set it


class AdjustmentCause(str, Enum):
    GATE_MET = "GATE_MET"  # evidence met the gate: a value added, or a numeric preference established
    BOUNDED_STEP = "BOUNDED_STEP"  # a new consistent batch moved a numeric preference by at most one step
    GATE_LOST = "GATE_LOST"  # the evidence no longer meets the gate: it was withdrawn or outweighed
    DISPLACED = "DISPLACED"  # still supported, but better-supported values fill the bounded list
    RECOMPUTED = "RECOMPUTED"  # changed evidence put the stored value off the new derivation's path


@dataclass(frozen=True)
class AdaptationPolicy:
    """Every Long-Term Adaptation Policy v1 constant. Change any of them and the version must change."""

    version: str = "adaptation-v1"

    # The gate (spec §23, D06), and how many distinct tracks the evidence must be about, so one song alone never
    # generalizes into a genre, mood, or feature preference.
    min_strong_signals: int = 4
    min_sessions: int = 2
    min_distinct_tracks: int = 2

    # Turns that steer the current session only and are no statement of taste: long-term evidence is read without them.
    session_only_turns: FrozenSet[TurnKind] = frozenset({TurnKind.MORE_LIKE_THIS})

    # What is strong: an explicit action at full Feedback Policy v1 strength (|weight| 1.00: Like, Save, Playlist add,
    # Replay, Not for me), or the 90-100% completion band (+0.80). Skips, partial plays, and grace-period plays never are.
    min_strong_explicit_weight: float = 1.0
    min_strong_passive_weight: float = 0.80

    # Bounds: how many genres (and moods) the profile keeps, and how far one batch moves a number.
    max_preferred_values: int = 3
    unit_coherence_span: float = 0.25  # energy, danceability, valence, acousticness: a batch's values within this
    tempo_coherence_span_bpm: float = 20.0
    max_unit_step: float = 0.05
    max_tempo_step_bpm: float = 5.0
    value_decimals: int = 4  # stored precision, so a recomputation compares equal

    def __post_init__(self) -> None:
        if not self.version or not self.version.strip():
            raise ValueError("an adaptation policy needs a version")
        if min(self.min_strong_signals, self.min_sessions, self.min_distinct_tracks, self.max_preferred_values, self.value_decimals) < 1:
            raise ValueError("the gate, the bounded list, and the precision must be at least 1")
        object.__setattr__(self, "session_only_turns", frozenset(TurnKind(kind) for kind in self.session_only_turns))
        if not 0.0 < self.min_strong_explicit_weight <= 1.0 or not 0.0 < self.min_strong_passive_weight <= 1.0:
            raise ValueError("strength thresholds are in (0, 1]")
        spans = (self.unit_coherence_span, self.max_unit_step)
        if any(not 0.0 < value <= 1.0 for value in spans) or self.tempo_coherence_span_bpm <= 0 or self.max_tempo_step_bpm <= 0:
            raise ValueError("coherence spans and steps must be positive, and the unit ones at most 1")

    def polarity(self, interpretation: Interpretation) -> int:
        """+1 for strong positive evidence, -1 for strong negative, 0 when it is not strong enough to count."""
        if interpretation.basis is EvidenceBasis.EXPLICIT:
            if interpretation.weight >= self.min_strong_explicit_weight:
                return 1
            if interpretation.weight <= -self.min_strong_explicit_weight:
                return -1
            return 0
        if interpretation.basis is EvidenceBasis.PASSIVE and interpretation.weight >= self.min_strong_passive_weight:
            return 1
        return 0

    def coherence_span(self, dimension: ProfileDimension) -> float:
        return self.tempo_coherence_span_bpm if dimension is ProfileDimension.TEMPO else self.unit_coherence_span

    def max_step(self, dimension: ProfileDimension) -> float:
        return self.max_tempo_step_bpm if dimension is ProfileDimension.TEMPO else self.max_unit_step


ADAPTATION_V1 = AdaptationPolicy()


# --- Evidence -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LongTermEvidence:
    """One strong effective item: what everything about one track in one session meant.

    The deciding raw fact is a feedback event or a NOT_FOR_ME / MORE_LIKE_THIS turn, exactly one of them.
    """

    session_id: str
    track_id: str
    weight: float
    at: datetime
    music: MusicCandidate
    feedback_event_id: Optional[str] = None
    session_turn_id: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.weight, bool) or not -1.0 <= self.weight <= 1.0 or self.weight == 0:
            raise ValueError("long-term evidence has a non-zero weight between -1 and 1")
        if (self.feedback_event_id is None) == (self.session_turn_id is None):
            raise ValueError("long-term evidence rests on exactly one raw fact: a feedback event or a turn")

    @property
    def polarity(self) -> int:
        return 1 if self.weight > 0 else -1


def strong_evidence(
    histories: Sequence[SessionHistory],
    tracks: Mapping[str, Track],
    policy: AdaptationPolicy = ADAPTATION_V1,
    feedback_policy: RecommendationPolicy = POLICY_V1,
) -> Tuple[LongTermEvidence, ...]:
    """Every strong effective item in these sessions, oldest first. A track the library no longer has gives none.

    Each session is read by Feedback Policy v1 without its session-only turns (More like this), so they never count
    toward a permanent change, and an earlier Like is not overruled by one.
    """
    items = []
    for history in histories:
        turns = [turn for turn in history.turns if turn.kind not in policy.session_only_turns]
        interpretations = interpretations_by_track(turns, history.occurrences, history.feedback_events, feedback_policy)
        for track_id, interpretation in interpretations.items():
            track = tracks.get(track_id)
            if track is None or policy.polarity(interpretation) == 0:
                continue
            items.append(LongTermEvidence(
                session_id=history.session.session_id,
                track_id=track_id,
                weight=interpretation.weight,
                at=interpretation.at,
                music=candidate_from_track(track).music,
                feedback_event_id=interpretation.event_id,
                session_turn_id=interpretation.turn_id,
            ))
    return tuple(sorted(items, key=lambda item: (item.at, item.session_id, item.track_id)))


# --- Deriving the profile -------------------------------------------------------------------------------


def _key(label: str) -> str:
    """A label as Policy v1 compares it: ignoring case and surrounding space."""
    return label.strip().casefold()


def _sessions(items: Sequence[LongTermEvidence]) -> int:
    return len({item.session_id for item in items})


def _tracks(items: Sequence[LongTermEvidence]) -> int:
    return len({item.track_id for item in items})


@dataclass(frozen=True)
class CategoricalSupport:
    """Everything strong said about one genre or mood value."""

    dimension: ProfileDimension
    value: str  # as the earliest evidence about it spells it
    positive: Tuple[LongTermEvidence, ...]
    negative: Tuple[LongTermEvidence, ...]

    @property
    def net(self) -> int:
        return len(self.positive) - len(self.negative)

    @property
    def sessions(self) -> int:
        """How many sessions the positive evidence comes from."""
        return _sessions(self.positive)

    @property
    def tracks(self) -> int:
        """How many distinct tracks the positive evidence is about."""
        return _tracks(self.positive)

    @property
    def evidence(self) -> Tuple[LongTermEvidence, ...]:
        return tuple(sorted(self.positive + self.negative, key=lambda item: (item.at, item.session_id, item.track_id)))

    def meets_gate(self, policy: AdaptationPolicy) -> bool:
        return (
            self.net >= policy.min_strong_signals
            and self.sessions >= policy.min_sessions
            and self.tracks >= policy.min_distinct_tracks
        )


@dataclass(frozen=True)
class NumericRound:
    """One consumed batch: the numeric preference before and after it."""

    dimension: ProfileDimension
    before: Optional[float]
    after: Optional[float]
    target: float  # the batch median
    polarity: int
    evidence: Tuple[LongTermEvidence, ...]

    @property
    def cause(self) -> AdjustmentCause:
        return AdjustmentCause.GATE_MET if self.before is None else AdjustmentCause.BOUNDED_STEP


@dataclass(frozen=True)
class DerivedProfile:
    """The profile the history supports, with the support and batches behind each part of it."""

    profile: UserProfile
    support: Mapping[ProfileDimension, Tuple[CategoricalSupport, ...]]
    rounds: Mapping[ProfileDimension, Tuple[NumericRound, ...]]
    evidence: Tuple[LongTermEvidence, ...]


def _categorical_support(evidence: Sequence[LongTermEvidence], dimension: ProfileDimension) -> Tuple[CategoricalSupport, ...]:
    feature = _CATEGORICAL[dimension][0]
    grouped: Dict[str, List[LongTermEvidence]] = {}
    for item in evidence:
        value = getattr(item.music, feature)
        if value is not None and value.strip():
            grouped.setdefault(_key(value), []).append(item)
    return tuple(
        CategoricalSupport(
            dimension=dimension,
            value=getattr(items[0].music, feature).strip(),
            positive=tuple(item for item in items if item.polarity > 0),
            negative=tuple(item for item in items if item.polarity < 0),
        )
        for _, items in sorted(grouped.items())
    )


def _preferred(support: Sequence[CategoricalSupport], policy: AdaptationPolicy) -> Tuple[str, ...]:
    """The values that meet the gate, at most max_preferred_values of them, the best supported first chosen."""
    qualifying = sorted((item for item in support if item.meets_gate(policy)), key=lambda item: _key(item.value))
    qualifying.sort(key=lambda item: (item.net, max(evidence.at for evidence in item.positive)), reverse=True)
    return tuple(sorted((item.value for item in qualifying[: policy.max_preferred_values]), key=_key))


def _latest_consistent_run(
    pending: Sequence[LongTermEvidence], feature: str, span: float
) -> List[LongTermEvidence]:
    """The newest items of the newest item's polarity whose values all lie within span, in time order."""
    newest = pending[-1]
    lowest = highest = getattr(newest.music, feature)
    run = [newest]
    for item in reversed(pending[:-1]):
        value = getattr(item.music, feature)
        if item.polarity != newest.polarity or max(highest, value) - min(lowest, value) > span:
            break
        lowest, highest = min(lowest, value), max(highest, value)
        run.append(item)
    return list(reversed(run))


def _moved(
    value: Optional[float], target: float, polarity: int, dimension: ProfileDimension, policy: AdaptationPolicy
) -> Optional[float]:
    step = policy.max_step(dimension)
    if polarity > 0:
        moved = target if value is None else value + max(-step, min(step, target - value))
    elif value is None or value == target:
        return value  # a rejection alone does not say where to go
    else:
        moved = value + (step if value > target else -step)
    lowest, highest = (step, float("inf")) if dimension is ProfileDimension.TEMPO else (0.0, 1.0)
    return round(max(lowest, min(highest, moved)), policy.value_decimals)


def _numeric_rounds(
    evidence: Sequence[LongTermEvidence], dimension: ProfileDimension, policy: AdaptationPolicy
) -> Tuple[NumericRound, ...]:
    feature = _NUMERIC[dimension][0]
    value: Optional[float] = None
    rounds: List[NumericRound] = []
    pending: List[LongTermEvidence] = []
    for item in evidence:
        if getattr(item.music, feature) is None:
            continue  # D21: a track without the feature says nothing about it
        pending = _latest_consistent_run(pending + [item], feature, policy.coherence_span(dimension))
        if (
            len(pending) < policy.min_strong_signals
            or _sessions(pending) < policy.min_sessions
            or _tracks(pending) < policy.min_distinct_tracks
        ):
            continue
        target = round(median(getattr(batch.music, feature) for batch in pending), policy.value_decimals)
        moved = _moved(value, target, item.polarity, dimension, policy)
        if moved != value:
            rounds.append(NumericRound(dimension, value, moved, target, item.polarity, tuple(pending)))
        value = moved
        pending = []  # consumed: this evidence never moves the preference again
    return tuple(rounds)


def derive_profile(evidence: Sequence[LongTermEvidence], policy: AdaptationPolicy = ADAPTATION_V1) -> DerivedProfile:
    """The long-term profile the strong evidence supports, from nothing: the same evidence always gives the same profile."""
    evidence = tuple(sorted(evidence, key=lambda item: (item.at, item.session_id, item.track_id)))
    support = {dimension: _categorical_support(evidence, dimension) for dimension in CATEGORICAL_DIMENSIONS}
    rounds = {dimension: _numeric_rounds(evidence, dimension, policy) for dimension in NUMERIC_DIMENSIONS}
    fields = {_CATEGORICAL[dimension][1]: _preferred(support[dimension], policy) for dimension in CATEGORICAL_DIMENSIONS}
    fields.update({_NUMERIC[dimension][1]: rounds[dimension][-1].after if rounds[dimension] else None for dimension in NUMERIC_DIMENSIONS})
    return DerivedProfile(profile=UserProfile(**fields), support=support, rounds=rounds, evidence=evidence)


# --- From the stored profile to the derived one --------------------------------------------------------

Value = Union[Tuple[str, ...], Optional[float]]


@dataclass(frozen=True)
class PlannedAdjustment:
    """One change to record: a dimension's value before and after, why, and the evidence behind it."""

    dimension: ProfileDimension
    change: AdjustmentChange
    cause: AdjustmentCause
    subject: Optional[str]  # the genre or mood added or removed; None for a numeric dimension
    previous: Value
    resulting: Value
    reason: str
    evidence: Tuple[LongTermEvidence, ...]


def _numeric_change(before: Optional[float], after: Optional[float]) -> AdjustmentChange:
    if before is None:
        return AdjustmentChange.SET
    if after is None:
        return AdjustmentChange.CLEARED
    return AdjustmentChange.RAISED if after > before else AdjustmentChange.LOWERED


def _label(dimension: ProfileDimension) -> str:
    return dimension.value.lower()


def _gate_text(support: CategoricalSupport, policy: AdaptationPolicy) -> str:
    return (
        f"{len(support.positive)} strong positive and {len(support.negative)} strong negative signals for "
        f"{_label(support.dimension)} '{support.value}': net {support.net} (needs {policy.min_strong_signals}), "
        f"positive evidence from {support.sessions} session(s) (needs {policy.min_sessions}) "
        f"about {support.tracks} track(s) (needs {policy.min_distinct_tracks})"
    )


def _round_reason(item: NumericRound, policy: AdaptationPolicy) -> str:
    batch = (
        f"{len(item.evidence)} consistent strong {'positive' if item.polarity > 0 else 'negative'} values from "
        f"{_sessions(item.evidence)} sessions and {_tracks(item.evidence)} tracks, median {item.target:g} (span at most "
        f"{policy.coherence_span(item.dimension):g})"
    )
    if item.before is None:
        return f"established {_label(item.dimension)} at {item.after:g}: the median of {batch}"
    direction = "toward" if item.polarity > 0 else "away from"
    return (
        f"moved {_label(item.dimension)} {direction} {item.target:g} by at most {policy.max_step(item.dimension):g} "
        f"({item.before:g} to {item.after:g}): a new batch of {batch}"
    )


def plan_adjustments(
    stored: Optional[UserProfile], derived: DerivedProfile, policy: AdaptationPolicy = ADAPTATION_V1
) -> Tuple[PlannedAdjustment, ...]:
    """The changes that take the stored profile to the derived one, each with its reason and evidence."""
    stored = stored if stored is not None else UserProfile()
    plans: List[PlannedAdjustment] = []

    for dimension in CATEGORICAL_DIMENSIONS:
        field_name = _CATEGORICAL[dimension][1]
        before, after = getattr(stored, field_name), getattr(derived.profile, field_name)
        support = {_key(item.value): item for item in derived.support[dimension]}
        after_keys, before_keys = {_key(value) for value in after}, {_key(value) for value in before}
        state = sorted(before, key=_key)
        for value in sorted(before, key=_key):
            if _key(value) in after_keys:
                continue
            item = support.get(_key(value))
            if item is not None and item.meets_gate(policy):
                cause = AdjustmentCause.DISPLACED
                reason = f"displaced: {_gate_text(item, policy)}; only the {policy.max_preferred_values} best-supported values are kept"
            else:
                cause = AdjustmentCause.GATE_LOST
                reason = f"no longer meets the gate: {_gate_text(item, policy)}" if item else f"no strong evidence remains for {_label(dimension)} '{value}'"
            previous = tuple(state)
            state.remove(value)
            plans.append(PlannedAdjustment(dimension, AdjustmentChange.REMOVED, cause, value, previous, tuple(state), reason, item.evidence if item else ()))
        for value in after:
            if _key(value) in before_keys:
                continue
            item = support[_key(value)]
            previous = tuple(state)
            state = sorted(state + [value], key=_key)
            plans.append(PlannedAdjustment(
                dimension, AdjustmentChange.ADDED, AdjustmentCause.GATE_MET, value, previous, tuple(state),
                f"meets the gate: {_gate_text(item, policy)}", item.evidence,
            ))

    for dimension in NUMERIC_DIMENSIONS:
        value = getattr(stored, _NUMERIC[dimension][1])
        rounds = derived.rounds[dimension]
        path = [None] + [item.after for item in rounds]
        if value == path[-1]:
            continue
        on_path = [index for index, step in enumerate(path) if step == value]
        if on_path:
            for item in rounds[on_path[-1]:]:
                plans.append(PlannedAdjustment(
                    dimension, _numeric_change(item.before, item.after), item.cause, None, item.before, item.after,
                    _round_reason(item, policy), item.evidence,
                ))
        else:
            final = path[-1]
            reason = (
                f"recomputed {_label(dimension)} from the current evidence ({value:g} to "
                f"{'nothing' if final is None else format(final, 'g')}): evidence behind the stored value was withdrawn or changed"
            )
            plans.append(PlannedAdjustment(
                dimension, _numeric_change(value, final), AdjustmentCause.RECOMPUTED, None, value, final, reason,
                tuple(evidence for item in rounds for evidence in item.evidence),
            ))
    return tuple(plans)


# --- What is stored ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceReference:
    """A stored pointer from an adjustment to one effective item: its session, track, weight, and deciding raw fact."""

    session_id: str
    track_id: str
    weight: float
    feedback_event_id: Optional[str] = None
    session_turn_id: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("session_id", "track_id"):
            require_canonical_uuid(getattr(self, name), name)
        for name in ("feedback_event_id", "session_turn_id"):
            if getattr(self, name) is not None:
                require_canonical_uuid(getattr(self, name), name)
        if (self.feedback_event_id is None) == (self.session_turn_id is None):
            raise ValueError("an evidence reference names exactly one raw fact: a feedback event or a turn")
        if isinstance(self.weight, bool) or not -1.0 <= self.weight <= 1.0 or self.weight == 0:
            raise ValueError("an evidence reference has a non-zero weight between -1 and 1")

    @classmethod
    def of(cls, item: LongTermEvidence) -> "EvidenceReference":
        return cls(item.session_id, item.track_id, item.weight, item.feedback_event_id, item.session_turn_id)


@dataclass(frozen=True)
class ProfileAdjustment:
    """One recorded change to a listener's long-term profile (append-only): what, why, under which policy, from what."""

    adjustment_id: str
    listener_profile_id: str
    sequence: int  # 1, 2, ... per listener: the order the changes were made in
    dimension: ProfileDimension
    change: AdjustmentChange
    cause: AdjustmentCause
    subject: Optional[str]
    previous: Value
    resulting: Value
    reason: str
    policy_version: str
    created_at: datetime
    evidence: Tuple[EvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        require_canonical_uuid(self.adjustment_id, "adjustment_id")
        require_canonical_uuid(self.listener_profile_id, "listener_profile_id")
        object.__setattr__(self, "dimension", ProfileDimension(self.dimension))
        object.__setattr__(self, "change", AdjustmentChange(self.change))
        object.__setattr__(self, "cause", AdjustmentCause(self.cause))
        object.__setattr__(self, "created_at", require_utc_datetime(self.created_at, "created_at"))
        require_text(self.reason, "reason")
        require_text(self.policy_version, "policy_version")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise ValueError("an adjustment's sequence starts at 1")
        categorical = self.dimension in _CATEGORICAL
        if categorical != (self.subject is not None):
            raise ValueError("a genre or mood adjustment names its value, and only those do")
        if categorical:
            object.__setattr__(self, "previous", tuple(self.previous))
            object.__setattr__(self, "resulting", tuple(self.resulting))
        object.__setattr__(self, "evidence", tuple(self.evidence))


@dataclass(frozen=True)
class LongTermProfile:
    """The listener's current long-term profile, as the adjustments left it. Recomputable from the history."""

    listener_profile_id: str
    profile: UserProfile
    policy_version: str
    updated_at: datetime

    def __post_init__(self) -> None:
        require_canonical_uuid(self.listener_profile_id, "listener_profile_id")
        require_text(self.policy_version, "policy_version")
        object.__setattr__(self, "updated_at", require_utc_datetime(self.updated_at, "updated_at"))
