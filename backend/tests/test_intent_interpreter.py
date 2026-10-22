"""The listening vocabulary and the deterministic interpreter of typed messages (B9). Pure: no database."""

import hashlib
import uuid
from datetime import datetime, timezone

import pytest

from src.intentune.adapters.deterministic_intent import DeterministicIntentInterpreter
from src.intentune.domain.intent import (
    CURATED_MOODS,
    DIMENSIONS,
    ENERGY_LEVELS,
    UNMAPPED_CONTEXT_FIELDS,
    DimensionState,
    LibraryCapability,
    MeaningKind,
    MessageMeaning,
    NotUnderstoodReason,
    Vocabulary,
    energy_level,
    stepped_energy,
    unavailable_dimensions,
    vocabulary_from_candidates,
    vocabulary_from_tracks,
)
from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.domain.models import ListeningContext, MusicCandidate
from src.intentune.domain.policy import Targets
from src.intentune.domain.session import FeedbackEventType, TurnKind

_NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
_VOCABULARY = Vocabulary(genres=("Afrobeats", "Hip-Hop/Rap", "Jazz"), library_moods=("Mellow",))
_interpreter = DeterministicIntentInterpreter()


def _read(text, context=None, vocabulary=_VOCABULARY):
    return _interpreter.interpret(text, context, vocabulary)


def _reason(text, context=None):
    meaning = _read(text, context)
    assert not meaning.understood
    return meaning.not_understood


# --- The vocabulary -----------------------------------------------------------------------------


def test_the_energy_scale_has_five_levels_of_fixed_targets():
    assert [(level.level_id, level.label, level.target_energy) for level in ENERGY_LEVELS] == [
        ("very-low", "Very low", 0.1),
        ("low", "Low", 0.3),
        ("medium", "Medium", 0.5),
        ("high", "High", 0.7),
        ("very-high", "Very high", 0.9),
    ]


@pytest.mark.parametrize("target, level_id", [(None, None), (0.1, "very-low"), (0.5, "medium"), (0.62, "high"), (0.0, "very-low"), (1.0, "very-high"), (0.4, "low")])
def test_a_target_belongs_to_its_nearest_level(target, level_id):
    level = energy_level(target)

    assert (level.level_id if level else None) == level_id


@pytest.mark.parametrize(
    "target, steps, expected",
    [(None, 1, 0.7), (None, -1, 0.3), (0.5, 1, 0.7), (0.9, 1, 0.9), (0.1, -1, 0.1), (0.3, -2, 0.1), (0.62, -1, 0.5)],
)
def test_energy_steps_by_levels_within_the_scale_from_medium_when_unset(target, steps, expected):
    assert stepped_energy(target, steps) == expected


def test_the_curated_moods_are_the_approved_designs():
    assert CURATED_MOODS == ("Emotional", "Focused", "Calm", "Joyful", "Driven")
    assert Vocabulary().tune_moods == CURATED_MOODS


def _track(genres=(), moods=(), status=TrackStatus.READY):
    labels = tuple(TrackLabel(LabelKind.GENRE, genre, "embedded_tags", index == 0) for index, genre in enumerate(genres))
    labels += tuple(TrackLabel(LabelKind.MOOD, mood, "embedded_tags", index == 0) for index, mood in enumerate(moods))
    return Track(
        track_id=str(uuid.uuid4()), sha256=hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest(), size_bytes=1,
        audio_format=AudioFormat.FLAC, status=status, original_filename="x.flac", created_at=_NOW, updated_at=_NOW, labels=labels,
    )


def test_the_vocabulary_is_what_the_policy_can_use_of_the_librarys_labels_ignoring_case():
    """Policy v1 reads each track's primary genre and mood, so those are the vocabulary; secondary labels are not."""
    vocabulary = vocabulary_from_tracks([_track(("jazz", "Blues")), _track(("Jazz ",), ("Mellow",)), _track(("Afrobeats",), ("mellow", "Calm"))])

    assert vocabulary.genres == ("Afrobeats", "jazz")  # Blues is only ever a secondary label
    assert vocabulary.library_moods == ("Mellow",)  # Calm is only ever a secondary label
    assert vocabulary.moods == ("Calm", "Driven", "Emotional", "Focused", "Joyful", "Mellow")  # curated and library, once each
    assert vocabulary.tune_moods == CURATED_MOODS  # Tune never shows library mood tags


def test_capability_is_what_the_policy_can_use_of_the_playable_library_now():
    genres_only = vocabulary_from_tracks([_track(("Jazz",)), _track(("Ambient",), ("Mellow",))])
    tune_mood = vocabulary_from_tracks([_track(("Jazz",), ("calm",))])

    assert genres_only.capability == LibraryCapability(playable_tracks=2, usable=("genre",))  # Mellow is not one of Tune's moods
    assert tune_mood.capability == LibraryCapability(playable_tracks=1, usable=("mood", "genre"))
    # Nothing fills the five measured features yet: they are unavailable for now, not removed.
    assert [genres_only.capability.state(dimension) for dimension in DIMENSIONS] == [
        DimensionState.NO_DATA, DimensionState.USABLE, *[DimensionState.NO_DATA] * 5
    ]


def test_a_library_with_nothing_playable_is_not_ready_rather_than_unsupported_dimension_by_dimension():
    for vocabulary in (vocabulary_from_tracks([]), vocabulary_from_tracks([_track(("Jazz",), ("Calm",), status=TrackStatus.MISSING_MANAGED_FILE)])):
        assert (vocabulary.genres, vocabulary.library_moods, vocabulary.capability) == ((), (), LibraryCapability())
        assert not vocabulary.capability.ready
        assert {vocabulary.capability.state(dimension) for dimension in DIMENSIONS} == {DimensionState.LIBRARY_NOT_READY}


def test_playable_tracks_without_usable_data_make_a_ready_library_whose_dimensions_have_no_data():
    capability = vocabulary_from_tracks([_track()]).capability

    assert (capability.ready, capability.playable_tracks, capability.usable) == (True, 1, ())
    assert {capability.state(dimension) for dimension in DIMENSIONS} == {DimensionState.NO_DATA}


def _candidate(**features):
    return MusicCandidate(candidate_id=str(uuid.uuid4()), title="t", creator="c", source="local", **features)


@pytest.mark.parametrize(
    "feature, value, dimension",
    [("energy", 0.4, "energy"), ("danceability", 0.6, "danceability"), ("tempo_bpm", 118.0, "tempo"), ("valence", 0.3, "valence"), ("acousticness", 0.9, "acousticness")],
)
def test_a_measured_dimension_becomes_usable_by_itself_once_a_candidate_carries_its_value(feature, value, dimension):
    """No pipeline fills these values yet. Once one does, through candidate_from_track(), the dimension is usable, with no other change."""
    assert vocabulary_from_candidates([_candidate()]).capability.usable == ()

    capability = vocabulary_from_candidates([_candidate(), _candidate(**{feature: value})]).capability

    assert capability.usable == (dimension,)
    assert capability.state(dimension) is DimensionState.USABLE


def test_a_capability_is_consistent_by_construction():
    assert LibraryCapability(3, ("energy", "genre", "mood")).usable == ("mood", "genre", "energy")  # always in DIMENSIONS order
    with pytest.raises(ValueError):
        LibraryCapability(0, ("genre",))  # nothing playable can use nothing
    with pytest.raises(ValueError):
        LibraryCapability(3, ("loudness",))
    with pytest.raises(ValueError):
        LibraryCapability(3).state("loudness")


def test_the_unmapped_context_fields_change_nothing_policy_v1_targets():
    """current_mood, listening_goal, and activity are kept and stored, but Policy v1 does not read them yet."""
    stated = ListeningContext(current_mood="tired", listening_goal="get through emails", activity="working", temporary_genres=("Jazz",))

    assert UNMAPPED_CONTEXT_FIELDS == ("current_mood", "listening_goal", "activity")
    assert Targets.effective(stated, None) == Targets.effective(ListeningContext(temporary_genres=("Jazz",)), None)


def test_a_mood_is_usable_only_when_a_playable_track_declares_it():
    vocabulary = vocabulary_from_tracks([_track(("Jazz",), ("Calm",))])

    assert vocabulary.mood_is_usable("calm") and not vocabulary.mood_is_usable("Focused")


# --- Meanings -------------------------------------------------------------------------------------


def test_a_meaning_holds_exactly_one_thing():
    with pytest.raises(ValueError):
        MessageMeaning(kind=MeaningKind.REFINE)
    with pytest.raises(ValueError):
        MessageMeaning(kind=MeaningKind.TURN, turn=TurnKind.REFINE)
    with pytest.raises(ValueError):
        MessageMeaning(kind=MeaningKind.REACTION, reaction=FeedbackEventType.SKIP)
    with pytest.raises(ValueError):
        MessageMeaning(kind=MeaningKind.SAVE_REQUESTED, not_understood=NotUnderstoodReason.UNRECOGNIZED)
    assert MessageMeaning.save_requested().understood
    assert not MessageMeaning.not_understood_because(NotUnderstoodReason.AMBIGUOUS).understood


# --- Commands -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("more like this", MessageMeaning.steering(TurnKind.MORE_LIKE_THIS)),
        ("More like that please", MessageMeaning.steering(TurnKind.MORE_LIKE_THIS)),
        ("surprise me", MessageMeaning.steering(TurnKind.SURPRISE_ME)),
        ("something more familiar", MessageMeaning.steering(TurnKind.MORE_FAMILIAR)),
        ("try something different", MessageMeaning.steering(TurnKind.TRY_SOMETHING_DIFFERENT)),
        ("play something different", MessageMeaning.steering(TurnKind.TRY_SOMETHING_DIFFERENT)),
        ("this is not for me", MessageMeaning.steering(TurnKind.NOT_FOR_ME)),
        ("skip this", MessageMeaning.steering(TurnKind.NEXT)),
        ("skip", MessageMeaning.steering(TurnKind.NEXT)),
        ("Next", MessageMeaning.steering(TurnKind.NEXT)),
        ("play that again", MessageMeaning.reacting(FeedbackEventType.REPLAY)),
        ("replay this", MessageMeaning.reacting(FeedbackEventType.REPLAY)),
        ("I like this", MessageMeaning.reacting(FeedbackEventType.LIKE)),
        ("love this!", MessageMeaning.reacting(FeedbackEventType.LIKE)),
        ("save this", MessageMeaning.save_requested()),
        ("SAVE", MessageMeaning.save_requested()),
    ],
)
def test_commands_map_to_their_structured_meaning(text, expected):
    assert _read(text) == expected


def test_longer_phrases_win_so_more_like_this_is_not_a_like():
    assert _read("more like this").turn is TurnKind.MORE_LIKE_THIS
    assert _read("Something different, please").turn is TurnKind.TRY_SOMETHING_DIFFERENT


@pytest.mark.parametrize("text", ["nextdoor vibes", "saved", "skipping", "unlike this", "dislike this"])
def test_phrases_match_whole_words_only(text):
    assert _reason(text) is NotUnderstoodReason.UNRECOGNIZED


# --- Refinements ----------------------------------------------------------------------------------


def test_energy_moves_one_level_from_the_current_target():
    calm = ListeningContext(target_energy=0.5, temporary_genres=("Jazz",))

    assert _read("a bit calmer", calm).context == ListeningContext(target_energy=0.3, temporary_genres=("Jazz",))
    assert _read("more energetic", calm).context.target_energy == 0.7
    assert _read("less energy").context.target_energy == 0.3  # from Medium when unset
    assert _read("MORE ENERGY").context.target_energy == 0.7


def test_a_genre_the_library_declares_is_set_as_the_genre():
    meaning = _read("more afrobeats", ListeningContext(temporary_genres=("Jazz",), temporary_moods=("Calm",)))

    assert meaning.kind is MeaningKind.REFINE
    assert meaning.context == ListeningContext(temporary_genres=("Afrobeats",), temporary_moods=("Calm",))
    assert _read("some hip-hop/rap").context.temporary_genres == ("Hip-Hop/Rap",)
    assert _read("any genre is fine", ListeningContext(temporary_genres=("Jazz",))).context.temporary_genres == ()


def test_a_genre_the_library_lacks_is_not_recognized():
    assert _reason("more amapiano") is NotUnderstoodReason.UNRECOGNIZED


def test_curated_and_library_moods_are_recognized():
    assert _read("I'm feeling focused").context.temporary_moods == ("Focused",)
    assert _read("something mellow").context.temporary_moods == ("Mellow",)
    assert _read("calm").context.temporary_moods == ("Calm",)
    assert _read("calmer").context.temporary_moods == ()  # an energy word, not the mood


def test_several_dimensions_change_in_one_refinement():
    meaning = _read("calmer jazz, something emotional", ListeningContext(target_energy=0.7))

    assert meaning.context == ListeningContext(target_energy=0.5, temporary_genres=("Jazz",), temporary_moods=("Emotional",))


def test_a_name_that_is_both_a_genre_and_a_mood_is_the_genre():
    vocabulary = Vocabulary(genres=("Chill",), library_moods=("Chill",))

    meaning = _interpreter.interpret("some chill", None, vocabulary)

    assert (meaning.context.temporary_genres, meaning.context.temporary_moods) == (("Chill",), ())


def test_the_rest_of_the_context_is_kept():
    context = ListeningContext(listening_goal="study", activity="reading", desired_mood="calm", target_tempo_bpm=90)

    changed = _read("more jazz", context).context

    assert (changed.listening_goal, changed.activity, changed.desired_mood, changed.target_tempo_bpm) == ("study", "reading", "calm", 90.0)


def test_curly_apostrophes_and_spacing_do_not_matter():
    assert _read("  I’d  LOVE   this  ").reaction is FeedbackEventType.LIKE


# --- What is refused ------------------------------------------------------------------------------


def test_language_outside_the_vocabulary_is_not_guessed():
    assert _reason("I want music that feels like driving through Accra at 2am after finishing my final exam") is NotUnderstoodReason.UNRECOGNIZED
    assert _reason("hello") is NotUnderstoodReason.UNRECOGNIZED


@pytest.mark.parametrize(
    "text",
    [
        "skip this and save it",
        "more like this but calmer",
        "surprise me with jazz",
        "jazz or afrobeats",
        "something calm and emotional",
        "calmer but more energetic",
    ],
)
def test_asking_for_several_or_opposite_things_at_once_is_ambiguous(text):
    assert _reason(text) is NotUnderstoodReason.AMBIGUOUS


@pytest.mark.parametrize("text", ["no jazz", "not jazz please", "anything without afrobeats", "less emotional", "never calm"])
def test_leaving_a_genre_or_mood_out_is_unsupported(text):
    assert _reason(text) is NotUnderstoodReason.UNSUPPORTED


def test_the_same_command_twice_is_one_command():
    assert _read("skip, skip this").turn is TurnKind.NEXT


# --- What the library can act on: one rule for every intent ---------------------------------------

_SOME_EVIDENCE = Vocabulary(genres=("Ambient",), library_moods=("Calm", "Mellow"), capability=LibraryCapability(3, ("mood", "genre")))


@pytest.mark.parametrize(
    "before, after, unavailable",
    [
        (ListeningContext(), ListeningContext(temporary_genres=(" ambient ",), temporary_moods=("CALM",)), ()),
        (ListeningContext(), ListeningContext(temporary_moods=("Joyful",)), ("mood",)),
        (ListeningContext(), ListeningContext(desired_mood="Joyful"), ("mood",)),
        (ListeningContext(), ListeningContext(temporary_genres=("Jazz",)), ("genre",)),
        (ListeningContext(), ListeningContext(target_energy=0.5), ("energy",)),
        (ListeningContext(), ListeningContext(temporary_genres=("Jazz",), temporary_moods=("Joyful",), target_energy=0.5), ("mood", "genre", "energy")),
        (ListeningContext(temporary_moods=("Joyful",), target_energy=0.5), ListeningContext(temporary_moods=("Joyful",), target_energy=0.5, temporary_genres=("Ambient",)), ()),
        (ListeningContext(temporary_genres=("Jazz",), temporary_moods=("Joyful",), target_energy=0.5), ListeningContext(), ()),
        (ListeningContext(desired_mood="Joyful"), ListeningContext(temporary_moods=("Joyful",)), ()),
        (ListeningContext(), ListeningContext(target_danceability=0.7, target_tempo_bpm=120, target_valence=0.4, target_acousticness=0.2), ("danceability", "tempo", "valence", "acousticness")),
        (ListeningContext(), ListeningContext(current_mood="tired", listening_goal="focus", activity="reading"), ()),
    ],
    ids=[
        "usable-as-policy-compares-labels", "mood", "desired-mood-is-a-mood", "undeclared-genre", "energy", "in-tunes-order",
        "unchanged-values-are-not-checked", "clearing-is-always-allowed", "the-same-moods-asked-another-way",
        "every-measured-target", "unmapped-fields-are-not-intent-dimensions",
    ],
)
def test_unavailable_dimensions_is_one_rule_for_every_intent(before, after, unavailable):
    assert unavailable_dimensions(before, after, _SOME_EVIDENCE) == unavailable


def test_the_usable_tune_moods_are_the_curated_ones_a_track_declares_in_tunes_order():
    assert Vocabulary(library_moods=("mellow", "joyful", "Calm")).usable_tune_moods == ("Calm", "Joyful")
    assert Vocabulary().usable_tune_moods == ()


def test_a_measured_target_is_acceptable_as_soon_as_the_library_has_that_feature():
    measured = Vocabulary(genres=("Ambient",), capability=LibraryCapability(3, ("genre", "energy", "valence")))

    assert unavailable_dimensions(ListeningContext(), ListeningContext(target_energy=0.7, target_valence=0.2), measured) == ()
    assert unavailable_dimensions(ListeningContext(), ListeningContext(target_energy=0.7, target_tempo_bpm=90), measured) == ("tempo",)
