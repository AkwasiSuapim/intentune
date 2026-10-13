import pytest

from src import main as main_module
from src.recommender import Recommender, Song, UserProfile as LegacyUserProfile
from src.intentune.domain.models import (
    FeatureWeights,
    ListeningContext,
    MusicCandidate,
    Recommendation,
    ScoreBreakdown,
    ScoreComponent,
    UserProfile,
)


# ---------------------------------------------------------------------------
# MusicCandidate
# ---------------------------------------------------------------------------


def test_music_candidate_valid_complete_candidate():
    candidate = MusicCandidate(
        candidate_id="1",
        title="Sunrise City",
        creator="Neon Echo",
        source="csv",
        genre="pop",
        mood="happy",
        energy=0.82,
        danceability=0.79,
        tempo_bpm=118,
        valence=0.84,
        acousticness=0.18,
        url="https://example.com/song",
        thumbnail_url="https://example.com/thumb.jpg",
    )

    assert candidate.candidate_id == "1"
    assert candidate.title == "Sunrise City"
    assert candidate.creator == "Neon Echo"
    assert candidate.source == "csv"
    assert candidate.genre == "pop"
    assert candidate.tempo_bpm == 118


def test_music_candidate_valid_with_missing_optional_audio_metadata():
    candidate = MusicCandidate(
        candidate_id="yt-123",
        title="Some Video",
        creator="Some Channel",
        source="youtube",
    )

    assert candidate.genre is None
    assert candidate.mood is None
    assert candidate.energy is None
    assert candidate.danceability is None
    assert candidate.tempo_bpm is None
    assert candidate.valence is None
    assert candidate.acousticness is None
    assert candidate.url is None
    assert candidate.thumbnail_url is None


def test_music_candidate_valid_non_csv_source():
    candidate = MusicCandidate(
        candidate_id="yt-456",
        title="Another Video",
        creator="Another Channel",
        source="youtube",
    )

    assert candidate.source == "youtube"


def test_music_candidate_rejects_blank_id():
    with pytest.raises(ValueError):
        MusicCandidate(candidate_id="   ", title="Title", creator="Creator", source="csv")


def test_music_candidate_rejects_blank_title():
    with pytest.raises(ValueError):
        MusicCandidate(candidate_id="1", title="   ", creator="Creator", source="csv")


def test_music_candidate_rejects_blank_creator():
    with pytest.raises(ValueError):
        MusicCandidate(candidate_id="1", title="Title", creator="  ", source="csv")


def test_music_candidate_rejects_blank_source():
    with pytest.raises(ValueError):
        MusicCandidate(candidate_id="1", title="Title", creator="Creator", source=" ")


def test_music_candidate_rejects_invalid_energy():
    with pytest.raises(ValueError):
        MusicCandidate(candidate_id="1", title="Title", creator="Creator", source="csv", energy=1.5)


def test_music_candidate_rejects_invalid_danceability():
    with pytest.raises(ValueError):
        MusicCandidate(candidate_id="1", title="Title", creator="Creator", source="csv", danceability=-0.1)


def test_music_candidate_rejects_invalid_valence():
    with pytest.raises(ValueError):
        MusicCandidate(candidate_id="1", title="Title", creator="Creator", source="csv", valence=2.0)


def test_music_candidate_rejects_invalid_acousticness():
    with pytest.raises(ValueError):
        MusicCandidate(candidate_id="1", title="Title", creator="Creator", source="csv", acousticness=-1.0)


def test_music_candidate_rejects_invalid_tempo():
    with pytest.raises(ValueError):
        MusicCandidate(candidate_id="1", title="Title", creator="Creator", source="csv", tempo_bpm=0)

    with pytest.raises(ValueError):
        MusicCandidate(candidate_id="1", title="Title", creator="Creator", source="csv", tempo_bpm=-10)


# ---------------------------------------------------------------------------
# UserProfile (canonical domain model)
# ---------------------------------------------------------------------------


def test_user_profile_valid_single_genre_and_mood():
    profile = UserProfile(preferred_genres=["pop"], preferred_moods=["happy"])

    assert profile.preferred_genres == ("pop",)
    assert profile.preferred_moods == ("happy",)


def test_user_profile_valid_multiple_genres_and_moods():
    profile = UserProfile(
        preferred_genres=["pop", "lofi", "jazz"],
        preferred_moods=["happy", "chill"],
    )

    assert profile.preferred_genres == ("pop", "lofi", "jazz")
    assert profile.preferred_moods == ("happy", "chill")


def test_user_profile_valid_with_optional_values_missing():
    profile = UserProfile()

    assert profile.preferred_genres == ()
    assert profile.preferred_moods == ()
    assert profile.preferred_energy is None
    assert profile.preferred_danceability is None
    assert profile.preferred_tempo_bpm is None
    assert profile.preferred_valence is None
    assert profile.preferred_acousticness is None


def test_user_profile_normalizes_duplicate_values_safely():
    profile = UserProfile(preferred_genres=["Pop", " pop ", "POP", "lofi"])

    assert profile.preferred_genres == ("Pop", "lofi")


def test_user_profile_rejects_blank_genre():
    with pytest.raises(ValueError):
        UserProfile(preferred_genres=["pop", "   "])


def test_user_profile_rejects_blank_mood():
    with pytest.raises(ValueError):
        UserProfile(preferred_moods=[""])


def test_user_profile_rejects_invalid_numerical_preferences():
    with pytest.raises(ValueError):
        UserProfile(preferred_energy=1.2)

    with pytest.raises(ValueError):
        UserProfile(preferred_danceability=-0.5)


def test_user_profile_rejects_invalid_tempo():
    with pytest.raises(ValueError):
        UserProfile(preferred_tempo_bpm=0)


# ---------------------------------------------------------------------------
# ListeningContext
# ---------------------------------------------------------------------------


def test_listening_context_valid_study_context():
    context = ListeningContext(
        listening_goal="study",
        activity="studying",
        target_energy=0.4,
        target_acousticness=0.7,
    )

    assert context.listening_goal == "study"
    assert context.target_energy == 0.4


def test_listening_context_valid_workout_context():
    context = ListeningContext(
        listening_goal="workout",
        activity="workout",
        target_energy=0.9,
        target_tempo_bpm=140,
    )

    assert context.activity == "workout"
    assert context.target_tempo_bpm == 140


def test_listening_context_valid_with_only_listening_goal():
    context = ListeningContext(listening_goal="discovery")

    assert context.listening_goal == "discovery"
    assert context.current_mood is None
    assert context.target_energy is None


def test_listening_context_rejects_invalid_numerical_targets():
    with pytest.raises(ValueError):
        ListeningContext(target_valence=2.0)

    with pytest.raises(ValueError):
        ListeningContext(target_tempo_bpm=-5)


def test_listening_context_rejects_invalid_blank_strings():
    with pytest.raises(ValueError):
        ListeningContext(current_mood="   ")

    with pytest.raises(ValueError):
        ListeningContext(listening_goal="")


# ---------------------------------------------------------------------------
# FeatureWeights
# ---------------------------------------------------------------------------


def test_feature_weights_valid():
    weights = FeatureWeights(genre=3.0, mood=3.0, energy=1.5, danceability=1.0, tempo=0.5, valence=0.5, acousticness=0.5)

    assert weights.genre == 3.0
    assert weights.total_active_weight == pytest.approx(10.0)


def test_feature_weights_zero_weight_allowed():
    weights = FeatureWeights(genre=0.0)

    assert weights.genre == 0.0


def test_feature_weights_rejects_negative_weight():
    with pytest.raises(ValueError):
        FeatureWeights(energy=-1.0)


def test_feature_weights_total_active_weight_calculation():
    weights = FeatureWeights(genre=2.0, mood=1.0)

    assert weights.total_active_weight == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# ScoreComponent
# ---------------------------------------------------------------------------


def test_score_component_valid():
    component = ScoreComponent(feature_name="genre", points_earned=3.0, maximum_points=3.0, reason="genre match")

    assert component.points_earned == 3.0


def test_score_component_rejects_negative_score():
    with pytest.raises(ValueError):
        ScoreComponent(feature_name="genre", points_earned=-1.0, maximum_points=3.0, reason="genre match")


def test_score_component_rejects_score_above_maximum():
    with pytest.raises(ValueError):
        ScoreComponent(feature_name="genre", points_earned=5.0, maximum_points=3.0, reason="genre match")


def test_score_component_rejects_blank_reason():
    with pytest.raises(ValueError):
        ScoreComponent(feature_name="genre", points_earned=3.0, maximum_points=3.0, reason="  ")


# ---------------------------------------------------------------------------
# ScoreBreakdown
# ---------------------------------------------------------------------------


def _sample_components():
    return [
        ScoreComponent(feature_name="genre", points_earned=3.0, maximum_points=3.0, reason="genre match"),
        ScoreComponent(feature_name="mood", points_earned=0.0, maximum_points=3.0, reason="mood did not match"),
        ScoreComponent(feature_name="energy", points_earned=1.5, maximum_points=2.0, reason="energy similarity"),
    ]


def test_score_breakdown_valid_consistent_breakdown():
    breakdown = ScoreBreakdown(total_score=4.5, maximum_score=8.0, components=_sample_components())

    assert breakdown.total_score == pytest.approx(4.5)
    assert breakdown.maximum_score == pytest.approx(8.0)


def test_score_breakdown_rejects_inconsistent_total():
    with pytest.raises(ValueError):
        ScoreBreakdown(total_score=5.0, maximum_score=8.0, components=_sample_components())


def test_score_breakdown_normalized_score_behavior():
    breakdown = ScoreBreakdown(total_score=0.0, maximum_score=0.0, components=[])
    assert breakdown.normalized_score is None

    breakdown = ScoreBreakdown(total_score=4.5, maximum_score=8.0, components=_sample_components())
    assert breakdown.normalized_score == pytest.approx(0.5625)


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


def _sample_candidate():
    return MusicCandidate(candidate_id="1", title="Title", creator="Creator", source="csv")


def _sample_breakdown():
    return ScoreBreakdown(total_score=3.0, maximum_score=3.0, components=[
        ScoreComponent(feature_name="genre", points_earned=3.0, maximum_points=3.0, reason="genre match"),
    ])


def test_recommendation_valid():
    recommendation = Recommendation(candidate=_sample_candidate(), score_breakdown=_sample_breakdown(), rank=1)

    assert recommendation.rank == 1


def test_recommendation_without_rank():
    recommendation = Recommendation(candidate=_sample_candidate(), score_breakdown=_sample_breakdown())

    assert recommendation.rank is None


def test_recommendation_rejects_invalid_rank():
    with pytest.raises(ValueError):
        Recommendation(candidate=_sample_candidate(), score_breakdown=_sample_breakdown(), rank=0)

    with pytest.raises(ValueError):
        Recommendation(candidate=_sample_candidate(), score_breakdown=_sample_breakdown(), rank=-1)


# ---------------------------------------------------------------------------
# Compatibility: legacy dataclass API must keep working, and the danceability
# bug must actually be fixed rather than silently hard-coded.
# ---------------------------------------------------------------------------


def _make_two_song_recommender() -> Recommender:
    return Recommender([
        Song(id=1, title="High Dance", artist="A", genre="pop", mood="happy", energy=0.8, tempo_bpm=120, valence=0.9, danceability=0.95, acousticness=0.1),
        Song(id=2, title="Low Dance", artist="B", genre="pop", mood="happy", energy=0.8, tempo_bpm=120, valence=0.9, danceability=0.05, acousticness=0.1),
    ])


def test_legacy_user_profile_default_danceability_preserves_old_hardcoded_behavior():
    profile = LegacyUserProfile(favorite_genre="pop", favorite_mood="happy", target_energy=0.8, likes_acoustic=False)

    assert profile.preferred_danceability == 0.5


def test_recommender_wrapper_actually_uses_preferred_danceability():
    rec = _make_two_song_recommender()

    high_dance_profile = LegacyUserProfile(
        favorite_genre="pop", favorite_mood="happy", target_energy=0.8, likes_acoustic=False, preferred_danceability=0.95,
    )
    low_dance_profile = LegacyUserProfile(
        favorite_genre="pop", favorite_mood="happy", target_energy=0.8, likes_acoustic=False, preferred_danceability=0.05,
    )

    results_favoring_high = rec.recommend(high_dance_profile, k=2)
    results_favoring_low = rec.recommend(low_dance_profile, k=2)

    assert results_favoring_high[0].title == "High Dance"
    assert results_favoring_low[0].title == "Low Dance"


def test_recommender_wrapper_no_longer_discards_scores_and_reasons():
    rec = _make_two_song_recommender()
    profile = LegacyUserProfile(favorite_genre="pop", favorite_mood="happy", target_energy=0.8, likes_acoustic=False)

    rec.recommend(profile, k=2)

    assert len(rec.last_recommendations) == 2
    assert all("score" in item and "reasons" in item for item in rec.last_recommendations)


def test_dictionary_based_functions_preserve_result_shape_for_domain_style_candidates():
    from src.recommender import recommend_songs

    user_prefs = {
        "favorite_genre": "pop",
        "favorite_mood": "happy",
        "preferred_energy": 0.8,
        "preferred_danceability": 0.8,
    }
    songs = [
        {"id": 1, "title": "A", "artist": "Artist", "genre": "pop", "mood": "happy", "energy": 0.8, "tempo_bpm": 120, "valence": 0.9, "danceability": 0.8, "acousticness": 0.1},
    ]

    recommendations = recommend_songs(user_prefs, songs, k=1)

    assert set(recommendations[0].keys()) == {"song", "score", "reasons"}


def test_cli_top_five_ranking_and_output_unchanged(capsys):
    main_module.main()

    output = capsys.readouterr().out
    titles_in_order = [line.split("—")[0].split(".", 1)[1].strip() for line in output.splitlines() if "—" in line]

    assert titles_in_order == [
        "Sunrise City",
        "Rooftop Lights",
        "Gym Hero",
        "Blinding Lights",
        "Calm Down",
    ]
