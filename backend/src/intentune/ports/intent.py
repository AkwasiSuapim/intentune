"""IntentInterpreter port (Prototype 1, phase B9): typed language -> a structured MessageMeaning.

Prototype 1's implementation is deterministic (adapters/deterministic_intent.py).
A future LLM-backed interpreter (D30, D39) would implement the same port,
leaving the session use cases, the recommendation policy, and the frontend
unchanged.
"""

from typing import Optional, Protocol

from src.intentune.domain.intent import MessageMeaning, Vocabulary
from src.intentune.domain.models import ListeningContext


class IntentInterpreter(Protocol):
    def interpret(self, text: str, context: Optional[ListeningContext], vocabulary: Vocabulary) -> MessageMeaning:
        """What the text means, given the context in force (None before a session starts).

        Must not guess: text it cannot map to the vocabulary is not understood.
        """
        ...
