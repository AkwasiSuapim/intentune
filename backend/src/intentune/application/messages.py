"""Application use cases: act on what the listener typed (Prototype 1, phase B9).

Typed language is the one input whose meaning the UI does not know (the B9
hybrid input decision). MessageService asks the IntentInterpreter port what
it means, then hands that structured meaning to the same use cases the
controls use. A typed "next" and a clicked Next both reach
ListeningService.next(), and a typed "like this" and a tapped Like both reach
FeedbackService.react(). There is no second implementation.

| Meaning | Use case |
|---|---|
| a refinement | ListeningService.steer(REFINE, the new context), or start() with it |
| a session control (surprise me, more familiar, try something different) | ListeningService.steer(control); at a start, start() with an empty context, then the control |
| MORE_LIKE_THIS | ListeningService.steer(MORE_LIKE_THIS) about the recommendation in view |
| NEXT | ListeningService.next(), with the player's facts when it gave them |
| NOT_FOR_ME | ListeningService.steer(NOT_FOR_ME) |
| LIKE, REPLAY | FeedbackService.react() |
| save requested | nothing changes; the UI asks which playlists. Only an explicit choice adds a track. |

"This" is the recommendation the listener has in view, which the UI names
(occurrence_id); without one it is the playing occurrence. A message about a
recommendation when there is none is not understood (NO_RECOMMENDATION).

Words are interpreted with IntentCapability's vocabulary. A refinement that
asks for what the library cannot act on (a mood no track declares, an energy
target) is understood, and then refused by the use case it reaches, with the
same IntentUnavailable a structured refine gets: there is one capability rule
(application/capability.py). Refusals name the dimensions the library can use,
so the guidance is honest. Nothing starts before the library is ready: a
first message in a library with no playable tracks answers LibraryNotReady,
whatever it says.

The text is interpreted and then dropped: only the structured turn or event
it leads to is stored (D33). A message that is not understood changes and
records nothing; MessageNotUnderstood says why.
"""

from dataclasses import dataclass
from typing import Optional

from src.intentune.application.capability import IntentCapability
from src.intentune.application.feedback import FeedbackOutcome, FeedbackService
from src.intentune.application.listening import ListeningService, PlaybackFacts
from src.intentune.application.sessions import SessionService
from src.intentune.domain.intent import (
    MeaningKind,
    MessageMeaning,
    MessageNotUnderstood,
    NotUnderstoodReason,
    Vocabulary,
)
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.session import SessionState, SessionTurn, TurnKind
from src.intentune.ports.intent import IntentInterpreter

# The controls that are about the session, not about a recommendation in it.
_SESSION_CONTROLS = frozenset({TurnKind.SURPRISE_ME, TurnKind.MORE_FAMILIAR, TurnKind.TRY_SOMETHING_DIFFERENT})


@dataclass(frozen=True)
class MessageOutcome:
    """What a message was taken to mean and what it did. turn and feedback are what was recorded, if anything."""

    meaning: MessageMeaning
    state: SessionState
    turn: Optional[SessionTurn] = None
    feedback: Optional[FeedbackOutcome] = None


class MessageService:
    def __init__(
        self,
        interpreter: IntentInterpreter,
        sessions: SessionService,
        listening: ListeningService,
        feedback: FeedbackService,
        capability: IntentCapability,
    ) -> None:
        self._interpreter = interpreter
        self._sessions = sessions
        self._listening = listening
        self._feedback = feedback
        self._capability = capability

    def start(self, listener_profile_id: str, text: str) -> MessageOutcome:
        """Start a session from the listener's first words. Refused, with nothing started, if they cannot be acted on."""
        vocabulary = self._capability.require_ready()  # nothing can start before there is music to play
        meaning = self._understood(text, None, vocabulary)
        if meaning.kind is MeaningKind.REFINE:
            return MessageOutcome(meaning, self._listening.start(listener_profile_id, meaning.context))
        if meaning.kind is MeaningKind.TURN and meaning.turn in _SESSION_CONTROLS:
            started = self._listening.start(listener_profile_id, ListeningContext())
            turn, state = self._listening.steer(started.session.session_id, meaning.turn)
            return MessageOutcome(meaning, state, turn=turn)
        raise self._refusal(NotUnderstoodReason.NO_RECOMMENDATION, vocabulary)

    def send(
        self,
        session_id: str,
        text: str,
        occurrence_id: Optional[str] = None,
        playback: Optional[PlaybackFacts] = None,
    ) -> MessageOutcome:
        """Act on a message in a session. occurrence_id is the recommendation in view; playback, how far it played."""
        current = self._sessions.get_session(session_id)
        vocabulary = self._capability.vocabulary()
        meaning = self._understood(text, current.session.current_context, vocabulary)
        about = occurrence_id or (current.playing.occurrence_id if current.playing is not None else None)

        if meaning.kind is MeaningKind.REFINE:
            turn, state = self._listening.steer(session_id, TurnKind.REFINE, context=meaning.context)
            return MessageOutcome(meaning, state, turn=turn)
        if meaning.kind is MeaningKind.TURN and meaning.turn in _SESSION_CONTROLS:
            turn, state = self._listening.steer(session_id, meaning.turn)
            return MessageOutcome(meaning, state, turn=turn)
        if about is None:
            raise self._refusal(NotUnderstoodReason.NO_RECOMMENDATION, vocabulary)
        if meaning.kind is MeaningKind.TURN and meaning.turn is TurnKind.NEXT:
            playing = current.playing.occurrence_id if current.playing is not None else None
            turn, state = self._listening.next(session_id, occurrence_id=playing, playback=playback if playing else None)
            return MessageOutcome(meaning, state, turn=turn)
        if meaning.kind is MeaningKind.TURN:  # NOT_FOR_ME, MORE_LIKE_THIS: about the recommendation in view
            turn, state = self._listening.steer(session_id, meaning.turn, occurrence_id=about)
            return MessageOutcome(meaning, state, turn=turn)
        if meaning.kind is MeaningKind.REACTION:
            outcome = self._feedback.react(session_id, about, meaning.reaction)
            return MessageOutcome(meaning, outcome.state, feedback=outcome)
        return MessageOutcome(meaning, current)  # save requested: the UI asks where

    def _understood(self, text: str, context: Optional[ListeningContext], vocabulary: Vocabulary) -> MessageMeaning:
        meaning = self._interpreter.interpret(text, context, vocabulary)
        if not meaning.understood:
            raise self._refusal(meaning.not_understood, vocabulary)
        return meaning

    @staticmethod
    def _refusal(reason: NotUnderstoodReason, vocabulary: Vocabulary) -> MessageNotUnderstood:
        return MessageNotUnderstood(reason, supported=vocabulary.capability.usable)
