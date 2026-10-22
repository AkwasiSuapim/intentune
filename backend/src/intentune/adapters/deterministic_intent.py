"""DeterministicIntentInterpreter: Prototype 1's interpreter of typed messages (B9; spec §11, D30).

A deliberately small vocabulary, matched on whole words and ignoring case.
Longer phrases are matched first, so "more like this" is never read as
"like this":

    more like this, more like that                    -> MORE_LIKE_THIS
    surprise me                                       -> SURPRISE_ME
    more familiar                                     -> MORE_FAMILIAR
    try something different, something different     -> TRY_SOMETHING_DIFFERENT
    not for me                                        -> NOT_FOR_ME
    skip this, skip, next                             -> NEXT
    play that again, play this again, replay this,
    replay                                            -> REPLAY
    like this, love this                              -> LIKE
    save this, save                                   -> save requested (the UI asks where)
    more energetic, more energy                       -> energy one level up
    calmer, less energetic, less energy               -> energy one level down
    a genre the library declares, or "any genre"      -> that genre (or none)
    a curated mood, or one the library declares       -> that mood

A message means one thing:
- a command (any of the first nine lines);
- or a refinement, which may change several dimensions at once ("calmer jazz").

Words outside the vocabulary are ignored. What cannot be read is refused,
never guessed:
- **Unrecognized:** nothing in the message is in the vocabulary.
- **Ambiguous:**
  - two commands, or a command mixed with a refinement;
  - two genres, or two moods;
  - energy both up and down.
- **Unsupported:** a genre or mood right after "no", "not", "without",
  "less", or "never", since excluding one cannot be expressed.

A name that is both a genre and a mood counts as the genre.
"""

import re
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

from src.intentune.domain.intent import MessageMeaning, NotUnderstoodReason, Vocabulary, stepped_energy
from src.intentune.domain.models import ListeningContext
from src.intentune.domain.session import FeedbackEventType, TurnKind

_COMMANDS: Tuple[Tuple[str, MessageMeaning], ...] = (
    ("more like this", MessageMeaning.steering(TurnKind.MORE_LIKE_THIS)),
    ("more like that", MessageMeaning.steering(TurnKind.MORE_LIKE_THIS)),
    ("surprise me", MessageMeaning.steering(TurnKind.SURPRISE_ME)),
    ("more familiar", MessageMeaning.steering(TurnKind.MORE_FAMILIAR)),
    ("try something different", MessageMeaning.steering(TurnKind.TRY_SOMETHING_DIFFERENT)),
    ("something different", MessageMeaning.steering(TurnKind.TRY_SOMETHING_DIFFERENT)),
    ("not for me", MessageMeaning.steering(TurnKind.NOT_FOR_ME)),
    ("skip this", MessageMeaning.steering(TurnKind.NEXT)),
    ("skip", MessageMeaning.steering(TurnKind.NEXT)),
    ("next", MessageMeaning.steering(TurnKind.NEXT)),
    ("play that again", MessageMeaning.reacting(FeedbackEventType.REPLAY)),
    ("play this again", MessageMeaning.reacting(FeedbackEventType.REPLAY)),
    ("replay this", MessageMeaning.reacting(FeedbackEventType.REPLAY)),
    ("replay", MessageMeaning.reacting(FeedbackEventType.REPLAY)),
    ("like this", MessageMeaning.reacting(FeedbackEventType.LIKE)),
    ("love this", MessageMeaning.reacting(FeedbackEventType.LIKE)),
    ("save this", MessageMeaning.save_requested()),
    ("save", MessageMeaning.save_requested()),
)
_ENERGY: Tuple[Tuple[str, int], ...] = (
    ("more energetic", 1),
    ("more energy", 1),
    ("less energetic", -1),
    ("less energy", -1),
    ("calmer", -1),
)
_ANY_GENRE = "any genre"
_NEGATIONS = frozenset({"no", "not", "without", "less", "never"})


@dataclass(frozen=True)
class _Match:
    start: int
    end: int
    category: str  # command, energy, genre, mood
    value: object


def _normalized(text: str) -> str:
    return " ".join(text.replace("’", "'").casefold().split())


def _phrases(vocabulary: Vocabulary) -> List[Tuple[str, str, object]]:
    phrases: List[Tuple[str, str, object]] = [(phrase, "command", meaning) for phrase, meaning in _COMMANDS]
    phrases += [(phrase, "energy", steps) for phrase, steps in _ENERGY]
    phrases.append((_ANY_GENRE, "genre", None))
    genres = {genre.casefold(): genre for genre in vocabulary.genres}
    phrases += [(name, "genre", genre) for name, genre in genres.items()]
    phrases += [(mood.casefold(), "mood", mood) for mood in vocabulary.moods if mood.casefold() not in genres]
    return phrases


def _matches(text: str, vocabulary: Vocabulary) -> List[_Match]:
    """Every vocabulary phrase in the text, longest first, never overlapping one already found."""
    found: List[_Match] = []
    for phrase, category, value in sorted(_phrases(vocabulary), key=lambda entry: -len(entry[0])):
        for hit in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", text):
            if all(hit.end() <= other.start or hit.start() >= other.end for other in found):
                found.append(_Match(hit.start(), hit.end(), category, value))
    return sorted(found, key=lambda match: match.start)


def _negated(text: str, match: _Match) -> bool:
    before = text[: match.start].split()
    return bool(before) and before[-1] in _NEGATIONS


class DeterministicIntentInterpreter:
    def interpret(self, text: str, context: Optional[ListeningContext], vocabulary: Vocabulary) -> MessageMeaning:
        text = _normalized(text)
        matches = _matches(text, vocabulary)
        commands = [match.value for match in matches if match.category == "command"]
        refinements = [match for match in matches if match.category != "command"]

        if commands:
            if len(set(commands)) > 1 or refinements:
                return MessageMeaning.not_understood_because(NotUnderstoodReason.AMBIGUOUS)
            return commands[0]
        if not refinements:
            return MessageMeaning.not_understood_because(NotUnderstoodReason.UNRECOGNIZED)
        if any(match.category in ("genre", "mood") and _negated(text, match) for match in refinements):
            return MessageMeaning.not_understood_because(NotUnderstoodReason.UNSUPPORTED)

        genres = {match.value for match in refinements if match.category == "genre"}
        moods = {match.value for match in refinements if match.category == "mood"}
        steps = {match.value for match in refinements if match.category == "energy"}
        if len(genres) > 1 or len(moods) > 1 or len(steps) > 1:
            return MessageMeaning.not_understood_because(NotUnderstoodReason.AMBIGUOUS)

        changed = context if context is not None else ListeningContext()
        if genres:
            [genre] = genres
            changed = replace(changed, temporary_genres=(genre,) if genre is not None else ())
        if moods:
            [mood] = moods
            changed = replace(changed, temporary_moods=(mood,))
        if steps:
            [step] = steps
            changed = replace(changed, target_energy=stepped_energy(changed.target_energy, step))
        return MessageMeaning.refine(changed)
