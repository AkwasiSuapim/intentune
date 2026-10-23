"""Long-term profile storage port (Prototype 1, phase B10). Implemented in persistence/repositories.py.

The profile is the current state; adjustments are append-only history, never
changed or deleted, each with its evidence references.
"""

from typing import List, Optional, Protocol

from src.intentune.domain.adaptation import LongTermProfile, ProfileAdjustment


class LongTermProfileRepository(Protocol):
    def get(self, listener_profile_id: str) -> Optional[LongTermProfile]:
        """The listener's current long-term profile, or None before the first adjustment."""
        ...

    def save(self, profile: LongTermProfile) -> None:
        """Store the profile, replacing the listener's previous one."""
        ...

    def add_adjustment(self, adjustment: ProfileAdjustment) -> None:
        """Append an adjustment and its evidence references."""
        ...

    def list_adjustments(self, listener_profile_id: str) -> List[ProfileAdjustment]:
        """Every adjustment of the listener, in sequence order, with its evidence in order."""
        ...

    def last_sequence(self, listener_profile_id: str) -> int:
        """The sequence of the listener's latest adjustment, 0 if there is none."""
        ...
