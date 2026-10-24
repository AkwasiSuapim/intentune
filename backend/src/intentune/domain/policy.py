"""Recommendation Policy v1 (Prototype 1, phases B5 and B6): choose the next three tracks for a session.

The stages run in the order of execution guide §8, each computed separately
so every decision can be explained (D07, D08):

    eligibility -> intent fit -> session fit -> long-term fit -> combine
                -> diversity / cooldown -> exploration -> top three (#2 may play first)

Session evidence comes from the session's turns and, since B6, its raw
feedback events, read through Feedback Policy v1 (interpret_feedback()).
Evidence is never stored: it is recomputed from the raw facts at every
refresh, so the feedback thresholds can change without losing anything.

Every heuristic constant is in RecommendationPolicy, versioned as a whole
("policy-v1"), Feedback Policy v1 included. They are Policy v1 heuristics,
not scientific facts (spec §15).

Rules that follow from the spec:

- Missing values are never invented (D21). A feature counts only when a
  target exists and the candidate has a value; the active feature weights
  are renormalized. A stage with nothing to compare is unavailable, and the
  stage weights (.55 intent, .30 session, .15 long-term) are renormalized.
- Current intent wins over long-term history (spec §14, §16). Intent fit
  scores the current ListeningContext only; the long-term profile is scored
  in its own stage, at .15. (B10: history never fills an intent target the
  listener left open. With B5's fill-in, a profile would have counted in both
  the .55 and the .15 stage and could outweigh this session's evidence,
  against D08, spec §16, and the B10 hierarchy. No profile existed before B10,
  so no earlier output changes.)
- A stored long-term preference is positive affinity, never a judgement of
  everything else (B10): the long-term stage scores
  long_term_neutral_fit + (1 - long_term_neutral_fit) * similarity, so a
  candidate that matches nothing in the profile is neutral (0.5), like a
  candidate session evidence says nothing about, and a full match is 1.0.
  Intent fit keeps its 0-1 scale (an explicit request may rightly score a
  mismatch 0), and session fit keeps its signed scale (evidence can be
  negative).
- Feature scoring reuses the legacy primitives (scoring.category_match and
  scoring.closeness), so there is one copy of the scoring math. With complete
  inputs and only the legacy four features targeted, intent fit equals
  score_candidate()'s normalized score.
- Session fit is net = sum(e * s * r) / sum(|e| * r) over session evidence,
  with r = 0.85 ** age (latest age 0), mapped to (clamp(net, -1, 1) + 1) / 2.
  No usable evidence gives 0.5.

Interpretation choices (TD-016):

- A candidate with nothing to score it on (no intent or long-term feature in
  common, and no evidence it can be compared with) has "no meaningful score"
  (spec §13). It never outranks a scorable candidate; it is used only to fill
  a queue the scorable candidates cannot fill, so music keeps flowing (D17).
- The recent-play cooldown shrinks for small libraries, so a finite library
  repeats tracks after a cooldown instead of running dry (D17). The playing
  track is never queued. A track that is eligible again only because the
  library is small is penalized, more the more recently it played, so a small
  library rotates through its tracks instead of alternating two of them.
- An explicitly requested genre is a finite library of its own (B11): its
  plays are held back by a cooldown bounded by its own available tracks, which
  leaves a queue's worth of them eligible. So a session keeps rotating through
  the genre instead of leaving it once a large library's cooldown covers every
  track in it. This only ever releases requested tracks earlier; it never holds
  any track back longer, and without a genre request nothing changes.
- "Near-duplicate" needs at least three features in common, so a library
  described by genre alone is not penalized as all-duplicates.
- Exploration happens two ways. Automatic exploration is random, at a rate
  near 10%, and never leaves an explicitly requested genre. A steering
  control (Surprise me, Try something different, More familiar) is a
  directive for the next refresh only, and it is deterministic. Surprise me
  takes the last slot for the best novel track within the genre, or, if the
  genre has none, outside it. Try something different takes a track outside
  the genre at once and makes it the next to play. More familiar suppresses
  exploration for that refresh. A refinement made before that refresh
  supersedes the control. Diversity never overrides intent; the listener's
  newer command changes it.
- Outside the genre, a track is judged on the rest of the intent and on the
  session's evidence. When nothing about it can be compared, it gets no
  score. It can still be a control's pick under an explicit fallback rule: it
  must be trustworthy (a known genre, and playable) and unrejected (not
  refused with Not for me in this session).
- A pick with no meaningful score is surfaced without a score.

Pure: no database or I/O. Randomness comes only from the injected rng.
"""

import random
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from src.intentune.domain.library import LabelKind, Track, TrackStatus
from src.intentune.domain.models import (
    FeatureWeights,
    ListeningContext,
    MusicCandidate,
    Recommendation,
    ScoreBreakdown,
    ScoreComponent,
    UserProfile,
)
from src.intentune.domain.scoring import category_match, closeness
from src.intentune.domain.session import (
    FeedbackEvent,
    FeedbackEventType,
    ListeningSession,
    RecommendationOccurrence,
    SessionTurn,
    TurnKind,
)

_UNIT_FEATURES = ("energy", "danceability", "valence", "acousticness")
_PLAYABLE = frozenset({TrackStatus.IMPORTED, TrackStatus.ANALYZING, TrackStatus.READY})
_EXPLORATION_CONTROLS = frozenset({TurnKind.SURPRISE_ME, TurnKind.TRY_SOMETHING_DIFFERENT, TurnKind.MORE_FAMILIAR})


def _legacy_feature_weights() -> FeatureWeights:
    # genre, mood, energy, danceability keep the legacy 3/3/2/2 proportions.
    return FeatureWeights(genre=3.0, mood=3.0, energy=2.0, danceability=2.0, tempo=1.0, valence=1.0, acousticness=1.0)


@dataclass(frozen=True)
class RecommendationPolicy:
    """Every Policy v1 constant. Change any of them and the version must change."""

    version: str = "policy-v1"
    queue_size: int = 3

    # Combined rank (spec §16).
    intent_weight: float = 0.55
    session_weight: float = 0.30
    long_term_weight: float = 0.15
    # A long-term preference is positive affinity (B10): no match is neutral, a full match is 1.0.
    long_term_neutral_fit: float = 0.5

    # Feature importance within a fit, and the tempo distance that counts as fully different.
    feature_weights: FeatureWeights = field(default_factory=_legacy_feature_weights)
    tempo_scale_bpm: float = 100.0

    # Session fit (spec §15).
    neutral_session_fit: float = 0.5
    recency_decay: float = 0.85

    # Feedback Policy v1 (spec §15, §17; decision register). Explicit actions first:
    like_weight: float = 1.0
    save_weight: float = 1.0
    playlist_add_weight: float = 1.0  # SAVE/PLAYLIST_ADD in the register (B7)
    replay_weight: float = 1.0
    not_for_me_weight: float = -1.0
    more_like_this_weight: float = 1.0  # the steering turn, as strong as Like
    # then passive playback: nothing for the first grace_seconds, then by the fraction played,
    # each band applying below its upper bound, and full_play_weight from the last bound up.
    grace_seconds: float = 8.0
    passive_bands: Tuple[Tuple[float, float], ...] = ((0.15, -0.50), (0.40, -0.20), (0.75, 0.10), (0.90, 0.50))
    full_play_weight: float = 0.80

    # Cooldown and diversity (spec §19). recent_play_penalty applies in full to the last play and
    # fades to nothing at cooldown_plays; it only matters when a small library shrinks the cooldown.
    cooldown_plays: int = 20
    recent_play_penalty: float = 0.10
    artist_repeat_penalty: float = 0.10
    near_duplicate_similarity: float = 0.95
    near_duplicate_min_features: int = 3
    near_duplicate_penalty: float = 0.15

    # Controlled exploration (spec §20). Automatic exploration runs at about 90/10, moved by how
    # recent exploration picks went. Listener controls are deterministic directives, with no rate.
    exploration_rate: float = 0.10
    max_exploration_rate: float = 0.50
    exploration_floor: float = 0.40
    novelty_similarity: float = 0.80
    exploration_outcome_window: int = 3
    exploration_failure_factor: float = 0.5
    exploration_success_factor: float = 1.25

    # Rolling top three (spec §21).
    swap_margin: float = 0.08

    def __post_init__(self) -> None:
        if not self.version or not self.version.strip():
            raise ValueError("a policy needs a version")
        if self.queue_size < 1 or self.cooldown_plays < 0 or self.exploration_outcome_window < 0:
            raise ValueError("queue_size must be positive; cooldown_plays and the outcome window non-negative")
        if self.near_duplicate_min_features < 1:
            raise ValueError("near_duplicate_min_features must be at least 1")
        stage_weights = (self.intent_weight, self.session_weight, self.long_term_weight)
        if any(weight < 0 for weight in stage_weights) or abs(sum(stage_weights) - 1.0) > 1e-9:
            raise ValueError("stage weights must be non-negative and sum to 1")
        fractions = (
            self.neutral_session_fit, self.long_term_neutral_fit, self.recency_decay, self.near_duplicate_similarity, self.exploration_rate,
            self.recent_play_penalty, self.artist_repeat_penalty, self.near_duplicate_penalty,
            self.max_exploration_rate, self.exploration_floor, self.novelty_similarity, self.swap_margin,
        )
        if any(not 0.0 <= value <= 1.0 for value in fractions):
            raise ValueError("rates, thresholds, penalties, and margins must be between 0 and 1")
        positive = (self.like_weight, self.save_weight, self.playlist_add_weight, self.replay_weight, self.more_like_this_weight)
        if not -1.0 <= self.not_for_me_weight <= 0.0 or any(not 0.0 <= weight <= 1.0 for weight in positive):
            raise ValueError("evidence weights are between -1 and 1, negative for Not for me and positive for the others")
        bounds = [bound for bound, _ in self.passive_bands]
        if self.grace_seconds < 0 or not self.passive_bands or bounds != sorted(set(bounds)) or not 0.0 < bounds[0] or bounds[-1] > 1.0:
            raise ValueError("grace_seconds must be non-negative and passive band bounds strictly increasing within (0, 1]")
        if any(not -1.0 <= weight <= 1.0 for _, weight in self.passive_bands) or not -1.0 <= self.full_play_weight <= 1.0:
            raise ValueError("passive weights are between -1 and 1")
        if self.tempo_scale_bpm <= 0 or self.exploration_failure_factor < 0 or self.exploration_success_factor < 0:
            raise ValueError("tempo scale must be positive and exploration factors non-negative")


POLICY_V1 = RecommendationPolicy()


# --- Inputs ------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyCandidate:
    """A library track as the policy sees it. music.candidate_id is the track id."""

    music: MusicCandidate
    artist: Optional[str] = None
    available: bool = True

    @property
    def track_id(self) -> str:
        return self.music.candidate_id


def candidate_from_track(track: Track) -> PolicyCandidate:
    """Project a library track. Only values the library actually has are set; the rest stay None (D21).

    The primary genre and mood labels become MusicCandidate.genre and .mood.
    Title and creator fall back to the file name and "Unknown artist" only
    because MusicCandidate requires them for display; an unknown artist is
    kept as None for diversity, so unknown artists never count as repeats.
    """
    def primary(kind: LabelKind) -> Optional[str]:
        labels = [label for label in track.labels if label.kind is kind]
        primaries = [label for label in labels if label.is_primary]
        return (primaries or labels)[0].value if labels else None

    music = MusicCandidate(
        candidate_id=track.track_id,
        title=track.title or track.original_filename,
        creator=track.artist or "Unknown artist",
        source="local",
        genre=primary(LabelKind.GENRE),
        mood=primary(LabelKind.MOOD),
    )
    return PolicyCandidate(music=music, artist=track.artist, available=track.status in _PLAYABLE)


@dataclass(frozen=True)
class SessionEvidence:
    """One piece of session evidence about a track: a weight from -1 (rejected) to 1 (wanted)."""

    track: MusicCandidate
    weight: float
    is_exploration: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)) or not -1.0 <= self.weight <= 1.0:
            raise ValueError("evidence weight must be between -1 and 1")


@dataclass(frozen=True)
class SessionSignals:
    """Everything the session tells the policy. Sequences are most recent first.

    pending_control is the steering control the next refresh must act on: a
    SURPRISE_ME, TRY_SOMETHING_DIFFERENT, or MORE_FAMILIAR turn that no
    surfaced queue and no refinement has followed yet. None otherwise.
    """

    context: ListeningContext = field(default_factory=ListeningContext)
    long_term: Optional[UserProfile] = None
    evidence: Tuple[SessionEvidence, ...] = ()
    excluded_track_ids: FrozenSet[str] = frozenset()
    recent_track_ids: Tuple[str, ...] = ()
    last_played: Optional[PolicyCandidate] = None
    pending_control: Optional[TurnKind] = None

    def __post_init__(self) -> None:
        if self.pending_control is not None and TurnKind(self.pending_control) not in _EXPLORATION_CONTROLS:
            raise ValueError("pending_control must be SURPRISE_ME, TRY_SOMETHING_DIFFERENT, or MORE_FAMILIAR")


# --- Feature fit and similarity ---------------------------------------------------------


def requested_moods(context: ListeningContext) -> Tuple[str, ...]:
    """The moods an intent asks for, as Policy v1 reads them: the temporary moods, or else the desired mood."""
    return context.temporary_moods or ((context.desired_mood,) if context.desired_mood else ())


@dataclass(frozen=True)
class Targets:
    """What each feature should be. Empty or None means no target for that feature."""

    genres: Tuple[str, ...] = ()
    moods: Tuple[str, ...] = ()
    energy: Optional[float] = None
    danceability: Optional[float] = None
    tempo_bpm: Optional[float] = None
    valence: Optional[float] = None
    acousticness: Optional[float] = None

    @classmethod
    def from_profile(cls, profile: Optional[UserProfile]) -> "Targets":
        if profile is None:
            return cls()
        return cls(
            genres=profile.preferred_genres,
            moods=profile.preferred_moods,
            energy=profile.preferred_energy,
            danceability=profile.preferred_danceability,
            tempo_bpm=profile.preferred_tempo_bpm,
            valence=profile.preferred_valence,
            acousticness=profile.preferred_acousticness,
        )

    @classmethod
    def from_context(cls, context: ListeningContext) -> "Targets":
        """What the current intent asks for, and nothing else: history is scored in its own stage (B10).

        current_mood, listening_goal, and activity are not read: their mapping into Policy v1 is unfinished (B9).
        """
        return cls(
            genres=context.temporary_genres,
            moods=requested_moods(context),
            energy=context.target_energy,
            danceability=context.target_danceability,
            tempo_bpm=context.target_tempo_bpm,
            valence=context.target_valence,
            acousticness=context.target_acousticness,
        )


@dataclass(frozen=True)
class FeatureScore:
    feature: str
    similarity: float
    weight: float


@dataclass(frozen=True)
class Fit:
    """A weighted average over the features that could be compared."""

    value: float
    features: Tuple[FeatureScore, ...]


def _weighted(scores: List[FeatureScore]) -> Optional[Fit]:
    active = [score for score in scores if score.weight > 0]
    total_weight = sum(score.weight for score in active)
    if total_weight == 0:
        return None
    return Fit(value=sum(score.similarity * score.weight for score in active) / total_weight, features=tuple(active))


def feature_fit(candidate: MusicCandidate, targets: Targets, policy: RecommendationPolicy = POLICY_V1) -> Optional[Fit]:
    """How well a candidate meets targets, over the features both sides have. None if none can be compared."""
    weights = policy.feature_weights
    scores = []
    if targets.genres and candidate.genre is not None:
        scores.append(FeatureScore("genre", 1.0 if category_match(candidate.genre, targets.genres) else 0.0, weights.genre))
    if targets.moods and candidate.mood is not None:
        scores.append(FeatureScore("mood", 1.0 if category_match(candidate.mood, targets.moods) else 0.0, weights.mood))
    for feature in _UNIT_FEATURES:
        target, value = getattr(targets, feature), getattr(candidate, feature)
        if target is not None and value is not None:
            scores.append(FeatureScore(feature, closeness(target, value), getattr(weights, feature)))
    if targets.tempo_bpm is not None and candidate.tempo_bpm is not None:
        scale = policy.tempo_scale_bpm
        scores.append(FeatureScore("tempo", closeness(targets.tempo_bpm / scale, candidate.tempo_bpm / scale), weights.tempo))
    return _weighted(scores)


@dataclass(frozen=True)
class Similarity:
    value: float
    feature_count: int


def _similarity_targets(candidate: MusicCandidate) -> Targets:
    """A candidate's own values as targets: what candidate_similarity() compares another candidate with."""
    return Targets(
        genres=(candidate.genre,) if candidate.genre is not None else (),
        moods=(candidate.mood,) if candidate.mood is not None else (),
        energy=candidate.energy,
        danceability=candidate.danceability,
        tempo_bpm=candidate.tempo_bpm,
        valence=candidate.valence,
        acousticness=candidate.acousticness,
    )


def _similarity(fit: Optional[Fit]) -> Optional[Similarity]:
    return Similarity(value=fit.value, feature_count=len(fit.features)) if fit is not None else None


def candidate_similarity(
    first: MusicCandidate, second: MusicCandidate, policy: RecommendationPolicy = POLICY_V1
) -> Optional[Similarity]:
    """How alike two candidates are, over only the features both have (spec §15). None if they share none."""
    return _similarity(feature_fit(first, _similarity_targets(second), policy))


# --- Session fit and combined score ---------------------------------------------------------


@dataclass(frozen=True)
class SessionFit:
    value: float
    has_evidence: bool


def session_fit(
    candidate: MusicCandidate, evidence: Sequence[SessionEvidence], policy: RecommendationPolicy = POLICY_V1
) -> SessionFit:
    return _session_fit(candidate, _evidence_targets(evidence), policy)


def _evidence_targets(evidence: Sequence[SessionEvidence]) -> Tuple[Tuple[float, Targets], ...]:
    """Each piece of evidence as its weight and its track's _similarity_targets(), most recent first."""
    return tuple((item.weight, _similarity_targets(item.track)) for item in evidence)


def _session_fit(
    candidate: MusicCandidate, evidence: Sequence[Tuple[float, Targets]], policy: RecommendationPolicy
) -> SessionFit:
    numerator = 0.0
    denominator = 0.0
    for age, (weight, targets) in enumerate(evidence):
        if weight == 0:
            continue
        fit = feature_fit(candidate, targets, policy)  # candidate_similarity() to the evidence track
        if fit is None:
            continue
        recency = policy.recency_decay ** age
        numerator += weight * fit.value * recency
        denominator += abs(weight) * recency
    if denominator == 0:
        return SessionFit(value=policy.neutral_session_fit, has_evidence=False)
    net = max(-1.0, min(1.0, numerator / denominator))
    return SessionFit(value=(net + 1.0) / 2.0, has_evidence=True)


@dataclass(frozen=True)
class PolicyScore:
    """The three stage scores and how they were combined. stage_weights are renormalized over available stages.

    long_term is the raw similarity to the stored profile; its stage value, in stage_weights, is that similarity read
    as positive affinity (long_term_stage_value()).
    """

    combined: float
    intent: Optional[Fit]
    session: SessionFit
    long_term: Optional[Fit]
    stage_weights: Tuple[Tuple[str, float, float], ...]

    @property
    def is_scorable(self) -> bool:
        """False when nothing about the candidate could be compared: no meaningful score (spec §13)."""
        return self.intent is not None or self.long_term is not None or self.session.has_evidence


def long_term_stage_value(similarity: float, policy: RecommendationPolicy = POLICY_V1) -> float:
    """A stored preference as positive affinity (B10): no match is neutral, a full match is 1.0, in between in proportion.

    The profile says what the listener has repeatedly liked, not that everything else is unwanted, so a candidate
    outside it is neutral in this stage, as a candidate session evidence says nothing about is neutral in that one.
    """
    return policy.long_term_neutral_fit + (1.0 - policy.long_term_neutral_fit) * similarity


def score(
    candidate: PolicyCandidate, signals: SessionSignals, policy: RecommendationPolicy = POLICY_V1, set_aside_genre: bool = False
) -> PolicyScore:
    """The staged score. set_aside_genre drops the genre target from intent fit, for a control that steps outside it."""
    return _Scorer(signals, policy, set_aside_genre).score(candidate)


def _features(music: MusicCandidate) -> Tuple[object, ...]:
    """Everything feature_fit() reads of a candidate. Candidates alike in all of it fit any targets alike."""
    return (music.genre, music.mood, music.energy, music.danceability, music.tempo_bpm, music.valence, music.acousticness)


class _Scorer:
    """score() for every candidate of one refresh (B11, same scores).

    The targets are read from the signals once, not once per candidate. A score depends only on the candidate's
    features (_features()), so candidates alike in all of them share one score, computed once: a library described
    by genre and mood labels has only a few dozen distinct ones, however many tracks it holds.
    """

    def __init__(self, signals: SessionSignals, policy: RecommendationPolicy, set_aside_genre: bool = False):
        intent = Targets.from_context(signals.context)
        self._intent = replace(intent, genres=()) if set_aside_genre else intent
        self._long_term = Targets.from_profile(signals.long_term)
        self._evidence = _evidence_targets(signals.evidence)
        self._policy = policy
        self._scores: Dict[Tuple[object, ...], PolicyScore] = {}

    def score(self, candidate: PolicyCandidate) -> PolicyScore:
        key = _features(candidate.music)
        known = self._scores.get(key)
        if known is None:
            known = self._scores[key] = self._compute(candidate.music)
        return known

    def _compute(self, music: MusicCandidate) -> PolicyScore:
        policy = self._policy
        intent = feature_fit(music, self._intent, policy)
        session = _session_fit(music, self._evidence, policy)
        long_term = feature_fit(music, self._long_term, policy)
        stages = [("session", policy.session_weight, session.value)]
        if intent is not None:
            stages.insert(0, ("intent", policy.intent_weight, intent.value))
        if long_term is not None:
            stages.append(("long_term", policy.long_term_weight, long_term_stage_value(long_term.value, policy)))
        total_weight = sum(weight for _, weight, _ in stages)
        normalized = tuple((name, weight / total_weight, value) for name, weight, value in stages)
        return PolicyScore(
            combined=sum(weight * value for _, weight, value in normalized),
            intent=intent,
            session=session,
            long_term=long_term,
            stage_weights=normalized,
        )


# --- Eligibility, diversity, exploration, top three ------------------------------------------


def cooldown_window(pool_size: int, policy: RecommendationPolicy = POLICY_V1) -> int:
    """How many of the most recently played tracks are held back: fewer in small libraries, never fewer than one."""
    return min(policy.cooldown_plays, max(1, pool_size - policy.queue_size))


def requested_cooldown_window(requested_count: int, policy: RecommendationPolicy = POLICY_V1) -> int:
    """How many of an explicitly requested genre's most recent plays are held back: all but a queue's worth of its
    available tracks, at most cooldown_plays. The track that just played is held back by cooldown_window() anyway."""
    return min(policy.cooldown_plays, max(0, requested_count - policy.queue_size))


def _released_from_cooldown(
    pool: Sequence[PolicyCandidate], recent: Sequence[str], signals: SessionSignals, policy: RecommendationPolicy
) -> FrozenSet[str]:
    """The requested genre's plays that its own cooldown lets go, so the genre does not run out (B11).

    recent is the pool's distinct plays, most recent first. The track playing (the session's latest play) is never
    released.
    """
    if not signals.context.temporary_genres:
        return frozenset()
    requested = {candidate.track_id for candidate in pool if _in_requested_genre(candidate, signals)}
    plays = [track_id for track_id in recent if track_id in requested]
    return frozenset(plays[requested_cooldown_window(len(requested), policy) :]) - frozenset(signals.recent_track_ids[:1])


def exploration_rate(signals: SessionSignals, policy: RecommendationPolicy = POLICY_V1) -> float:
    """The automatic exploration rate: the base rate, scaled by how recent exploration picks went (spec §18, §20).

    Listener controls do not move it. They are deterministic directives for the next refresh (see decide()).
    """
    outcomes = [item.weight for item in signals.evidence if item.is_exploration and item.weight != 0]
    rate = policy.exploration_rate
    for weight in outcomes[: policy.exploration_outcome_window]:
        rate *= policy.exploration_failure_factor if weight < 0 else policy.exploration_success_factor
    return max(0.0, min(policy.max_exploration_rate, rate))


def _same_artist(first: Optional[str], second: Optional[str]) -> bool:
    return first is not None and second is not None and first.casefold() == second.casefold()


@dataclass(frozen=True)
class RankedPick:
    """One queued track. An exploration pick for which the requested genre was set aside
    (genre_set_aside) carries the score it was judged on: the intent without that genre, or,
    under the fallback rule, a score that is not meaningful (score.is_scorable is False)."""

    candidate: PolicyCandidate
    score: PolicyScore
    ranking_score: float
    rank: int
    is_exploration: bool = False
    penalties: Tuple[str, ...] = ()
    genre_set_aside: bool = False


@dataclass(frozen=True)
class PolicyDecision:
    """The queue in play order, and why it looks the way it does.

    steering is the listener control this refresh acted on, if any. exploration_rate
    is the automatic rate, which is not used when a control is acted on.
    """

    picks: Tuple[RankedPick, ...]
    policy_version: str
    exploration_rate: float
    explored: bool
    second_plays_first: bool
    steering: Optional[TurnKind] = None

    @property
    def exploration_track_ids(self) -> FrozenSet[str]:
        return frozenset(pick.candidate.track_id for pick in self.picks if pick.is_exploration)

    def recommendations(self) -> List[Recommendation]:
        """The picks as canonical Recommendations, in play order, for SessionService.queue_recommendations().

        A pick with no meaningful score gets an empty breakdown, so it is surfaced without a score.
        """
        recommendations = []
        for pick in self.picks:
            components = tuple(
                ScoreComponent(feature_name=name, points_earned=weight * value, maximum_points=weight, reason=f"{name} fit {value:.2f}")
                for name, weight, value in pick.score.stage_weights
            ) if pick.score.is_scorable else ()
            breakdown = ScoreBreakdown(
                total_score=sum(component.points_earned for component in components),
                maximum_score=sum(component.maximum_points for component in components),
                components=components,
            )
            recommendations.append(Recommendation(candidate=pick.candidate.music, score_breakdown=breakdown, rank=pick.rank))
        return recommendations


def _tie_break(candidate: PolicyCandidate):
    return (candidate.music.title.lower(), candidate.music.creator.lower(), candidate.track_id)


class _Ranker:
    def __init__(self, recent_age: Mapping[str, int], policy: RecommendationPolicy):
        self.recent_age = recent_age  # plays ago, 0 for the latest, for tracks within cooldown_plays
        self.policy = policy
        self._targets: Dict[str, Targets] = {}  # each reference's _similarity_targets(), built once
        self._similarities: Dict[Tuple[str, Tuple[object, ...]], Optional[Similarity]] = {}  # as in _Scorer

    def similarity(self, candidate: PolicyCandidate, reference: PolicyCandidate) -> Optional[Similarity]:
        """candidate_similarity(candidate, reference), once per reference and distinct candidate features."""
        key = (reference.track_id, _features(candidate.music))
        if key not in self._similarities:
            targets = self._targets.get(reference.track_id)
            if targets is None:
                targets = self._targets[reference.track_id] = _similarity_targets(reference.music)
            self._similarities[key] = _similarity(feature_fit(candidate.music, targets, self.policy))
        return self._similarities[key]

    def penalties(self, candidate: PolicyCandidate, references: Sequence[PolicyCandidate]) -> Tuple[float, Tuple[str, ...]]:
        total = 0.0
        reasons = []
        age = self.recent_age.get(candidate.track_id)
        if age is not None:
            total += self.policy.recent_play_penalty * (1 - age / self.policy.cooldown_plays)
            reasons.append("recently played")
        if any(_same_artist(candidate.artist, reference.artist) for reference in references):
            total += self.policy.artist_repeat_penalty
            reasons.append("repeated artist")
        for reference in references:
            similarity = self.similarity(candidate, reference)
            if (
                similarity is not None
                and similarity.feature_count >= self.policy.near_duplicate_min_features
                and similarity.value >= self.policy.near_duplicate_similarity
            ):
                total += self.policy.near_duplicate_penalty
                reasons.append("near-duplicate")
                break
        return total, tuple(reasons)

    def is_novel(self, candidate: PolicyCandidate, references: Sequence[PolicyCandidate]) -> bool:
        for reference in references:
            if _same_artist(candidate.artist, reference.artist):
                return False
            similarity = self.similarity(candidate, reference)
            if similarity is not None and similarity.value >= self.policy.novelty_similarity:
                return False
        return True


def decide(
    candidates: Sequence[PolicyCandidate],
    signals: SessionSignals,
    policy: RecommendationPolicy = POLICY_V1,
    rng: Optional[random.Random] = None,
) -> PolicyDecision:
    """Choose up to queue_size tracks, in play order, for a session."""
    rng = rng if rng is not None else random.Random()

    # 1. Eligibility: available, not rejected in this session, not in the recent-play cooldown.
    #    Only plays of tracks still in the pool count, so a rejected track does not use up the cooldown.
    #    A requested genre's own plays are held back only as long as its own tracks allow.
    pool = [candidate for candidate in candidates if candidate.available and candidate.track_id not in signals.excluded_track_ids]
    pool_ids = {candidate.track_id for candidate in pool}
    recent = [track_id for track_id in dict.fromkeys(signals.recent_track_ids) if track_id in pool_ids][: policy.cooldown_plays]
    cooling = set(recent[: cooldown_window(len(pool), policy)]) - _released_from_cooldown(pool, recent, signals, policy)
    eligible = [candidate for candidate in pool if candidate.track_id not in cooling]
    ranker = _Ranker({track_id: age for age, track_id in enumerate(recent)}, policy)

    # 2-5. Intent, session, long-term, combined.
    scorer = _Scorer(signals, policy)
    scored = {candidate.track_id: scorer.score(candidate) for candidate in eligible}
    by_combined = sorted(
        eligible, key=lambda candidate: (not scored[candidate.track_id].is_scorable, -scored[candidate.track_id].combined, _tie_break(candidate))
    )
    combined_rank = {candidate.track_id: position for position, candidate in enumerate(by_combined, start=1)}

    # 6. Diversity: greedy selection against what just played and what is already chosen.
    #    remaining stays in combined order and a penalty only lowers a score, so once a candidate's unpenalized
    #    key cannot beat the best so far, no later candidate can: the scan stops there, with the same choice (B11).
    last = [signals.last_played] if signals.last_played is not None else []
    picks: List[RankedPick] = []
    remaining = list(by_combined)
    while remaining and len(picks) < policy.queue_size:
        references = last + [pick.candidate for pick in picks]
        best = None
        for candidate in remaining:
            candidate_score = scored[candidate.track_id]
            if best is not None and (not candidate_score.is_scorable, -candidate_score.combined, _tie_break(candidate)) >= best[0]:
                break
            penalty, reasons = ranker.penalties(candidate, references)
            key = (not candidate_score.is_scorable, -(candidate_score.combined - penalty), _tie_break(candidate))
            if best is None or key < best[0]:
                best = (key, candidate, penalty, reasons)
        _, chosen, penalty, reasons = best
        picks.append(
            RankedPick(chosen, scored[chosen.track_id], scored[chosen.track_id].combined - penalty, len(picks) + 1, penalties=reasons)
        )
        remaining.remove(chosen)

    # 7. Exploration.
    #    Automatic: at the automatic rate, the last slot goes to a plausible, novel track within the
    #    requested genre.
    #    A pending control decides instead, deterministically, without the random draw:
    #    More familiar explores nothing, Surprise me takes the last slot, and Try something different
    #    puts its track first, to play next.
    #    A queue that is not full already holds every eligible track, so there is nothing to explore.
    #    Nor can exploration pick a recent play: the cooldown holds those back, except in a small
    #    library or a small requested genre, where the cooldown leaves exactly a queue's worth of tracks.
    rate = exploration_rate(signals, policy)
    control = signals.pending_control
    explored = False
    if len(picks) == policy.queue_size:
        kept = picks[:-1]
        chosen_ids = {pick.candidate.track_id for pick in picks}
        others = [candidate for candidate in by_combined if candidate.track_id not in chosen_ids]
        references = last + [pick.candidate for pick in kept]
        choice = None
        if control in (TurnKind.SURPRISE_ME, TurnKind.TRY_SOMETHING_DIFFERENT):
            choice = _directed_choice(control, others, scored, signals, policy, ranker, references)
        elif control is None and rate > 0 and rng.random() < rate:
            choice = _within_genre_choice(others, scored, signals, policy, ranker, references)
        if choice is not None:
            explore, explore_score, genre_set_aside = choice
            pick = RankedPick(
                explore, explore_score, explore_score.combined, combined_rank[explore.track_id],
                is_exploration=True, genre_set_aside=genre_set_aside,
            )
            picks = [pick] + kept if control is TurnKind.TRY_SOMETHING_DIFFERENT else kept + [pick]
            explored = True

    # 8. Top three: #2 may play first when it is close to #1 and usefully more novel. Never when an
    #    exploration pick is involved, and an unscored #2 never goes ahead of a scored #1.
    second_first = (
        len(picks) >= 2
        and not picks[0].is_exploration
        and not picks[1].is_exploration
        and (picks[1].score.is_scorable or not picks[0].score.is_scorable)
        and picks[0].ranking_score - picks[1].ranking_score <= policy.swap_margin
        and _more_novel(picks[1].candidate, picks[0].candidate, signals.last_played, policy)
    )
    if second_first:
        picks = [picks[1], picks[0]] + picks[2:]

    return PolicyDecision(
        picks=tuple(picks),
        policy_version=policy.version,
        exploration_rate=rate,
        explored=explored,
        second_plays_first=second_first,
        steering=control,
    )


def _in_requested_genre(candidate: PolicyCandidate, signals: SessionSignals) -> bool:
    """Whether the track is in a genre the current intent explicitly asks for (always true when it names none)."""
    requested = signals.context.temporary_genres
    return not requested or (candidate.music.genre is not None and category_match(candidate.music.genre, requested))


_Choice = Optional[Tuple[PolicyCandidate, PolicyScore, bool]]  # the pick, its score, whether the genre was set aside


def _within_genre_choice(
    others: Sequence[PolicyCandidate],
    scored: Mapping[str, PolicyScore],
    signals: SessionSignals,
    policy: RecommendationPolicy,
    ranker: "_Ranker",
    references: Sequence[PolicyCandidate],
) -> _Choice:
    """The best scored, plausible (at or above the floor), novel track within the requested genre."""
    for candidate in others:  # in combined order, best first
        candidate_score = scored[candidate.track_id]
        if (
            _in_requested_genre(candidate, signals)
            and candidate_score.is_scorable
            and candidate_score.combined >= policy.exploration_floor
            and ranker.is_novel(candidate, references)
        ):
            return candidate, candidate_score, False
    return None


def _directed_choice(
    control: TurnKind,
    others: Sequence[PolicyCandidate],
    scored: Mapping[str, PolicyScore],
    signals: SessionSignals,
    policy: RecommendationPolicy,
    ranker: "_Ranker",
    references: Sequence[PolicyCandidate],
) -> _Choice:
    """A control's pick. Surprise me looks within the requested genre first; Try something different does not."""
    if control is TurnKind.SURPRISE_ME:
        within = _within_genre_choice(others, scored, signals, policy, ranker, references)
        if within is not None:
            return within
    return _outside_genre_choice(others, signals, policy, ranker, references)


def _fallback_eligible(candidate: PolicyCandidate) -> bool:
    """The explicit fallback rule for a control's pick that nothing can score. It is a rule, not a score: no value is invented.

    Trustworthy: a known genre from the track's own labels, and playable. Unrejected: not
    refused with Not for me in this session. Every candidate here has passed eligibility,
    which already requires playable and not refused, so only the genre is left to check.
    """
    return candidate.music.genre is not None


def _outside_genre_choice(
    others: Sequence[PolicyCandidate],
    signals: SessionSignals,
    policy: RecommendationPolicy,
    ranker: "_Ranker",
    references: Sequence[PolicyCandidate],
) -> _Choice:
    """The best novel track judged with the requested genre set aside.

    A track is judged on what can still be compared: the rest of the intent, the
    session's evidence, the long-term profile. If something can, it needs a score at
    or above the plausibility floor, so a genre the listener rejected stays out. If
    nothing can, it has no score and qualifies only under the fallback rule. Tracks
    with a score come first.
    """
    scorer = _Scorer(signals, policy, set_aside_genre=True)
    set_aside = {candidate.track_id: scorer.score(candidate) for candidate in others}
    novel = [candidate for candidate in others if ranker.is_novel(candidate, references)]
    with_score = sorted(
        (
            candidate
            for candidate in novel
            if set_aside[candidate.track_id].is_scorable and set_aside[candidate.track_id].combined >= policy.exploration_floor
        ),
        key=lambda candidate: (-set_aside[candidate.track_id].combined, _tie_break(candidate)),
    )
    by_rule = [candidate for candidate in novel if not set_aside[candidate.track_id].is_scorable and _fallback_eligible(candidate)]
    options = with_score + by_rule
    if not options:
        return None
    return options[0], set_aside[options[0].track_id], bool(signals.context.temporary_genres)


def _more_novel(
    second: PolicyCandidate, first: PolicyCandidate, last: Optional[PolicyCandidate], policy: RecommendationPolicy
) -> bool:
    """Whether #2 moves further from what just played than #1 does. Without a track played, there is nothing to compare."""
    if last is None or _same_artist(second.artist, last.artist):
        return False
    if _same_artist(first.artist, last.artist):
        return True
    second_similarity = candidate_similarity(second.music, last.music, policy)
    first_similarity = candidate_similarity(first.music, last.music, policy)
    if second_similarity is None or first_similarity is None:
        return False
    return second_similarity.value < first_similarity.value


# --- Feedback Policy v1: what feedback means ---------------------------------------------------


class EvidenceBasis(str, Enum):
    """What an occurrence's evidence rests on."""

    EXPLICIT = "EXPLICIT"  # Like, Save, Playlist add, Replay, Not for me, More like this
    PASSIVE = "PASSIVE"  # how much of it was played, after the grace period
    GRACE = "GRACE"  # played for the grace period or less: no preference evidence
    NONE = "NONE"  # nothing was said or played


@dataclass(frozen=True)
class Interpretation:
    """What everything the listener did about one track in a session means under Feedback Policy v1.

    Two separate things:
    - weight (from -1 to 1; 0 is no preference evidence) is the track's
      effective evidence, decided by the latest explicit action or else the
      latest playback. at is when that deciding signal was given, and
      occurrence_id which occurrence of the track it was about.
    - excluded is True once the track has been refused with Not for me in this
      session, whatever came after. It stays out of automatic recommendations
      for the rest of the session (D18). A later Like or Replay changes its
      evidence, and a Replay may still play it manually, but neither makes it
      eligible again.
    """

    weight: float
    basis: EvidenceBasis
    excluded: bool = False
    at: Optional[datetime] = None
    occurrence_id: Optional[str] = None
    # The raw fact that decided the weight: a feedback event, or a NOT_FOR_ME / MORE_LIKE_THIS turn (B10 audit).
    event_id: Optional[str] = None
    turn_id: Optional[str] = None


def passive_weight(played_seconds: float, played_fraction: float, policy: RecommendationPolicy = POLICY_V1) -> float:
    """Passive playback evidence (spec §17): nothing within the grace period, then by the fraction played."""
    if played_seconds <= policy.grace_seconds:
        return 0.0
    for upper_bound, weight in policy.passive_bands:
        if played_fraction < upper_bound:
            return weight
    return policy.full_play_weight


def _explicit_event_weight(event_type: FeedbackEventType, policy: RecommendationPolicy) -> Optional[float]:
    return {
        FeedbackEventType.LIKE: policy.like_weight,
        FeedbackEventType.SAVE: policy.save_weight,
        FeedbackEventType.PLAYLIST_ADD: policy.playlist_add_weight,
        FeedbackEventType.REPLAY: policy.replay_weight,
        FeedbackEventType.NOT_FOR_ME: policy.not_for_me_weight,
    }.get(event_type)


_PASSIVE_EVENTS = frozenset({FeedbackEventType.SKIP, FeedbackEventType.COMPLETE})


def event_weight(event: FeedbackEvent, policy: RecommendationPolicy = POLICY_V1) -> float:
    """What one event means on its own. An explicit action keeps its weight whatever was played.

    UNLIKE (B9) is neutral: 0.00. It is no preference of its own; it only cancels an earlier Like.
    """
    explicit = _explicit_event_weight(event.event_type, policy)
    if explicit is not None:
        return explicit
    if event.event_type not in _PASSIVE_EVENTS:
        return 0.0
    return passive_weight(event.played_seconds, event.played_fraction, policy)


def _uncancelled(events: Sequence[FeedbackEvent]) -> List[FeedbackEvent]:
    """The events that still count, in time order. An UNLIKE cancels every Like before it and is itself no evidence."""
    kept: List[FeedbackEvent] = []
    for event in sorted(events, key=lambda event: event.occurred_at):
        if event.event_type is FeedbackEventType.UNLIKE:
            kept = [earlier for earlier in kept if earlier.event_type is not FeedbackEventType.LIKE]
        else:
            kept.append(event)
    return kept


def interpret_feedback(
    turns: Sequence[SessionTurn], events: Sequence[FeedbackEvent], policy: RecommendationPolicy = POLICY_V1
) -> Interpretation:
    """Combine everything said and played about one track in a session (callers pass only those turns and events).

    The evidence: explicit actions take precedence over passive playback, and the
    latest explicit action decides, so the evidence follows a listener who changes
    their mind. Without one, the latest playback event decides.

    The exclusion is separate and sticky: any Not for me in the session, turn or
    event, keeps the track out of automatic recommendations for the rest of the
    session (D18), even if a later action outweighs it as evidence.

    An Unlike (B9) takes back the Likes before it: they no longer count, and the
    rest of the evidence decides, as if they had not been given. The Unlike is not
    a preference of its own, so it never reads as Not for me and leaves a
    Not-for-me exclusion as it was.

    It is about the track, across its occurrences, because a refresh surfaces the
    same upcoming track as a new occurrence: a Like on the queued card and the
    skip when it later plays are about the same listening. The raw events stay
    stored per occurrence.
    """
    excluded = any(turn.kind is TurnKind.NOT_FOR_ME for turn in turns) or any(
        event.event_type is FeedbackEventType.NOT_FOR_ME for event in events
    )
    events = _uncancelled(events)
    explicit = [
        (
            turn.created_at,
            policy.not_for_me_weight if turn.kind is TurnKind.NOT_FOR_ME else policy.more_like_this_weight,
            turn.occurrence_id,
            None,
            turn.turn_id,
        )
        for turn in turns
        if turn.kind in (TurnKind.NOT_FOR_ME, TurnKind.MORE_LIKE_THIS)
    ]
    explicit += [
        (event.occurred_at, _explicit_event_weight(event.event_type, policy), event.occurrence_id, event.event_id, None)
        for event in events
        if _explicit_event_weight(event.event_type, policy) is not None
    ]
    if explicit:
        at, weight, occurrence_id, event_id, turn_id = max(explicit, key=lambda signal: signal[0])
        return Interpretation(
            weight=weight, basis=EvidenceBasis.EXPLICIT, excluded=excluded, at=at, occurrence_id=occurrence_id,
            event_id=event_id, turn_id=turn_id,
        )
    passive = [event for event in events if event.event_type in _PASSIVE_EVENTS]
    if passive:
        latest = max(passive, key=lambda event: event.occurred_at)
        basis = EvidenceBasis.GRACE if latest.played_seconds <= policy.grace_seconds else EvidenceBasis.PASSIVE
        return Interpretation(
            weight=event_weight(latest, policy), basis=basis, at=latest.occurred_at, occurrence_id=latest.occurrence_id,
            event_id=latest.event_id,
        )
    return Interpretation(weight=0.0, basis=EvidenceBasis.NONE)


# --- From a session's history to signals ------------------------------------------------------


def interpretations_by_track(
    turns: Sequence[SessionTurn],
    occurrences: Sequence[RecommendationOccurrence],
    feedback_events: Sequence[FeedbackEvent],
    policy: RecommendationPolicy = POLICY_V1,
) -> Dict[str, Interpretation]:
    """Feedback Policy v1's reading of one session, per track: everything said or played about it, combined.

    The one place a session's raw history becomes per-track evidence. Session fit
    (signals_from_session) and long-term adaptation (domain/adaptation.py) both read
    it, so they cannot disagree about what the listener meant. Tracks nothing was
    said or played about are absent.
    """
    track_of = {occurrence.occurrence_id: occurrence.track_id for occurrence in occurrences}
    turns_about: Dict[str, List[SessionTurn]] = {}
    for turn in turns:
        if turn.occurrence_id in track_of:
            turns_about.setdefault(track_of[turn.occurrence_id], []).append(turn)
    events_about: Dict[str, List[FeedbackEvent]] = {}
    for event in feedback_events:
        if event.occurrence_id in track_of:
            events_about.setdefault(track_of[event.occurrence_id], []).append(event)
    return {
        track_id: interpret_feedback(turns_about.get(track_id, ()), events_about.get(track_id, ()), policy)
        for track_id in sorted(set(turns_about) | set(events_about))
    }


def signals_from_session(
    session: ListeningSession,
    turns: Sequence[SessionTurn],
    occurrences: Sequence[RecommendationOccurrence],
    tracks: Mapping[str, Track],
    policy: RecommendationPolicy = POLICY_V1,
    long_term: Optional[UserProfile] = None,
    feedback_events: Sequence[FeedbackEvent] = (),
) -> SessionSignals:
    """What the policy needs from a session's turns, occurrences, and feedback events.

    - Evidence: everything said or played about each track in the session is
      read through Feedback Policy v1 (interpret_feedback()). That gives one piece
      of evidence per track, newest first by when its deciding signal was given,
      and an exploration outcome when that signal was about an exploration pick.
      A track refused with Not for me at any point in the session is excluded
      from automatic recommendations for the rest of it, even if later feedback
      outweighs the refusal as evidence (spec §17, D18). Nothing is changed
      beyond the session.
    - Plays (PLAYING and PLAYED occurrences) feed the cooldown and diversity.
    - A SURPRISE_ME, TRY_SOMETHING_DIFFERENT, or MORE_FAMILIAR turn is a
      directive for the next refresh only. It is pending until a queue is
      surfaced after it, which acts on it; a listener's replay is not a surfaced
      queue. A refinement made before then restates the whole intent and
      supersedes the control, and so does a newer control. Within a session,
      SessionService gives every change a strictly later time, so "after" is
      exact even when the clock has not moved.
    """
    by_id: Dict[str, RecommendationOccurrence] = {occurrence.occurrence_id: occurrence for occurrence in occurrences}
    newest_first = sorted(turns, key=lambda turn: turn.sequence, reverse=True)

    dated_evidence = []
    excluded = set()
    for track_id, interpretation in interpretations_by_track(turns, occurrences, feedback_events, policy).items():
        if interpretation.excluded:
            excluded.add(track_id)
        track = tracks.get(track_id)
        if interpretation.weight != 0 and track is not None:
            exploration = by_id[interpretation.occurrence_id].is_exploration  # how the listener met it
            dated_evidence.append((interpretation.at, SessionEvidence(candidate_from_track(track).music, interpretation.weight, exploration)))
    evidence = tuple(item for _, item in sorted(dated_evidence, key=lambda dated: dated[0], reverse=True))

    plays = sorted((occurrence for occurrence in occurrences if occurrence.started_at is not None), key=lambda o: o.started_at, reverse=True)
    recent = tuple(occurrence.track_id for occurrence in plays)
    last_track = tracks.get(recent[0]) if recent else None
    last_surfaced = max(
        (occurrence.surfaced_at for occurrence in occurrences if not occurrence.is_listener_replay), default=None
    )
    pending = None
    for turn in newest_first:
        if last_surfaced is not None and turn.created_at <= last_surfaced:
            break  # a queue was surfaced after this turn, so an earlier control has been acted on
        if turn.kind in _EXPLORATION_CONTROLS:
            pending = turn.kind
            break
        if turn.kind in (TurnKind.REFINE, TurnKind.INITIAL_INTENT):
            break  # a refinement supersedes a control made before it

    return SessionSignals(
        context=session.current_context,
        long_term=long_term,
        evidence=evidence,
        excluded_track_ids=frozenset(excluded),
        recent_track_ids=recent,
        last_played=candidate_from_track(last_track) if last_track is not None else None,
        pending_control=pending,
    )
