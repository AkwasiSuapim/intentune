"""Application use case: keep a listener's long-term profile true to their history (Prototype 1, phase B10).

adapt() derives the profile from the listener's whole persisted history with
Long-Term Adaptation Policy v1 (domain/adaptation.py), compares it with the
stored profile, appends one adjustment per difference, each with its reason,
policy version, and evidence references, and stores the new profile. One
transaction.

It runs right after a raw fact that can change a track's long-term evidence
is persisted (any feedback event; a Not for me turn), and before that use
case's single queue refresh:

    persist raw feedback -> adapt() -> the one refresh_queue()

so the refresh already ranks with the new profile, and adapting never
refreshes anything itself. React does not train it, and nothing else writes
the profile.

Reversible and drift-free because it recomputes from the whole history every
time: an Unlike that withdraws a Like takes back the change the Like
supported, as a new recorded adjustment (nothing is deleted), and evidence
already consumed by the derivation never moves the profile again.

Cost: one read of the listener's history per relevant event: three queries
for the whole history and one for the tracks it mentions, whatever its size
(B11; the measurements are in docs/quality/evaluation-report.md).
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Tuple, TypeVar

from src.intentune.domain.adaptation import (
    ADAPTATION_V1,
    AdaptationPolicy,
    DerivedProfile,
    EvidenceReference,
    LongTermProfile,
    ProfileAdjustment,
    derive_profile,
    plan_adjustments,
    strong_evidence,
)
from src.intentune.domain.models import UserProfile
from src.intentune.domain.policy import POLICY_V1, RecommendationPolicy
from src.intentune.domain.session import SessionHistory, SessionNotFound
from src.intentune.domain.validation import new_uuid
from src.intentune.ports.unit_of_work import UnitOfWork


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


T = TypeVar("T")


def _by_session(items: Iterable[T]) -> Dict[str, Tuple[T, ...]]:
    """A listener-wide read split by session, each session's items in the order read."""
    grouped: Dict[str, List[T]] = defaultdict(list)
    for item in items:
        grouped[item.session_id].append(item)
    return {session_id: tuple(values) for session_id, values in grouped.items()}


class LongTermAdaptationService:
    def __init__(
        self,
        unit_of_work: UnitOfWork,
        policy: AdaptationPolicy = ADAPTATION_V1,
        feedback_policy: RecommendationPolicy = POLICY_V1,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._uow = unit_of_work
        self._policy = policy
        self._feedback_policy = feedback_policy  # the Feedback Policy v1 session fit reads evidence with
        self._clock = clock

    @property
    def policy(self) -> AdaptationPolicy:
        return self._policy

    def profile(self, listener_profile_id: str) -> Optional[UserProfile]:
        """The stored long-term profile, as Policy v1 receives it; None before the first adjustment."""
        stored = self.stored(listener_profile_id)
        return stored.profile if stored is not None else None

    def stored(self, listener_profile_id: str) -> Optional[LongTermProfile]:
        with self._uow:
            return self._uow.long_term_profiles.get(listener_profile_id)

    def adjustments(self, listener_profile_id: str) -> List[ProfileAdjustment]:
        """The audit trail: every adjustment, in order, with its evidence references."""
        with self._uow:
            return self._uow.long_term_profiles.list_adjustments(listener_profile_id)

    def derive(self, listener_profile_id: str) -> DerivedProfile:
        """What the history supports now, computed from scratch. Read-only."""
        with self._uow:
            return self._derive(listener_profile_id)

    def adapt_after(self, session_id: str) -> Tuple[ProfileAdjustment, ...]:
        """adapt() for the listener whose session just recorded something."""
        with self._uow:
            session = self._uow.listening_sessions.get(session_id)
            if session is None:
                raise SessionNotFound(session_id)
        return self.adapt(session.listener_profile_id)

    def adapt(self, listener_profile_id: str) -> Tuple[ProfileAdjustment, ...]:
        """Bring the stored profile in line with the history, recording every change. No change, no record."""
        with self._uow:
            derived = self._derive(listener_profile_id)
            stored = self._uow.long_term_profiles.get(listener_profile_id)
            plans = plan_adjustments(stored.profile if stored is not None else None, derived, self._policy)
            if not plans and (stored is None or stored.policy_version == self._policy.version):
                return ()
            now = self._clock()
            sequence = self._uow.long_term_profiles.last_sequence(listener_profile_id)
            adjustments = []
            for plan in plans:
                sequence += 1
                adjustment = ProfileAdjustment(
                    adjustment_id=new_uuid(),
                    listener_profile_id=listener_profile_id,
                    sequence=sequence,
                    dimension=plan.dimension,
                    change=plan.change,
                    cause=plan.cause,
                    subject=plan.subject,
                    previous=plan.previous,
                    resulting=plan.resulting,
                    reason=plan.reason,
                    policy_version=self._policy.version,
                    created_at=now,
                    evidence=tuple(EvidenceReference.of(item) for item in plan.evidence),
                )
                self._uow.long_term_profiles.add_adjustment(adjustment)
                adjustments.append(adjustment)
            self._uow.long_term_profiles.save(LongTermProfile(listener_profile_id, derived.profile, self._policy.version, now))
            self._uow.commit()
        return tuple(adjustments)

    def _derive(self, listener_profile_id: str) -> DerivedProfile:
        turns = _by_session(self._uow.session_turns.list_for_listener(listener_profile_id))
        occurrences = _by_session(self._uow.recommendation_occurrences.list_for_listener(listener_profile_id))
        events = _by_session(self._uow.feedback_events.list_for_listener(listener_profile_id))
        histories = [
            SessionHistory(
                session=session,
                turns=turns.get(session.session_id, ()),
                occurrences=occurrences.get(session.session_id, ()),
                feedback_events=events.get(session.session_id, ()),
            )
            for session in self._uow.listening_sessions.list_for_listener(listener_profile_id)
        ]
        # Evidence is only ever about a track the history surfaced, so only those tracks are read.
        mentioned = {occurrence.track_id for history in histories for occurrence in history.occurrences}
        tracks = {track.track_id: track for track in self._uow.tracks.get_many(mentioned)}
        return derive_profile(strong_evidence(histories, tracks, self._policy, self._feedback_policy), self._policy)
