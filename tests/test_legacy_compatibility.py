import pytest

from src import main as main_module
from src.recommender import (
    legacy_profile_to_user_profile,
    load_songs,
    recommend_songs,
    song_dict_to_music_candidate,
)
from src.intentune.adapters.csv_catalog import load_music_candidates
from src.intentune.application.recommendation_service import recommend_music
from src.intentune.domain.models import UserProfile


DEFAULT_LEGACY_PROFILE = {
    "favorite_genre": "pop",
    "favorite_mood": "happy",
    "preferred_energy": 0.80,
    "preferred_danceability": 0.80,
}

EXPECTED_TOP_FIVE = [
    ("Sunrise City", "Neon Echo", 9.94),
    ("Rooftop Lights", "Indigo Parade", 6.88),
    ("Gym Hero", "Max Pulse", 6.58),
    ("Blinding Lights", "The Weeknd", 3.86),
    ("Calm Down", "Rema", 3.86),
]


# ---------------------------------------------------------------------------
# Legacy profile conversion (section 6)
# ---------------------------------------------------------------------------


def test_valid_legacy_profile_conversion():
    profile = legacy_profile_to_user_profile(DEFAULT_LEGACY_PROFILE)

    assert isinstance(profile, UserProfile)
    assert profile.preferred_genres == ("pop",)
    assert profile.preferred_moods == ("happy",)
    assert profile.preferred_energy == 0.80
    assert profile.preferred_danceability == 0.80


def test_legacy_profile_conversion_missing_field_raises_key_error():
    incomplete = dict(DEFAULT_LEGACY_PROFILE)
    del incomplete["preferred_danceability"]

    with pytest.raises(KeyError):
        legacy_profile_to_user_profile(incomplete)


def test_legacy_profile_conversion_rejects_blank_genre():
    profile = dict(DEFAULT_LEGACY_PROFILE, favorite_genre="   ")

    with pytest.raises(ValueError):
        legacy_profile_to_user_profile(profile)


def test_legacy_profile_conversion_rejects_blank_mood():
    profile = dict(DEFAULT_LEGACY_PROFILE, favorite_mood="")

    with pytest.raises(ValueError):
        legacy_profile_to_user_profile(profile)


def test_legacy_profile_conversion_rejects_invalid_numerical_range():
    profile = dict(DEFAULT_LEGACY_PROFILE, preferred_energy=1.5)

    with pytest.raises(ValueError):
        legacy_profile_to_user_profile(profile)


def test_legacy_profile_conversion_normalizes_case_and_whitespace():
    profile = legacy_profile_to_user_profile(dict(DEFAULT_LEGACY_PROFILE, favorite_genre="  Pop  "))

    assert profile.preferred_genres == ("Pop",)


def test_canonical_profile_supports_multiple_preferences_even_though_legacy_supplies_one():
    converted = legacy_profile_to_user_profile(DEFAULT_LEGACY_PROFILE)
    assert len(converted.preferred_genres) == 1

    multi = UserProfile(preferred_genres=("pop", "lofi", "jazz"), preferred_moods=("happy", "chill"))
    assert len(multi.preferred_genres) == 3


# ---------------------------------------------------------------------------
# Legacy song-dict conversion
# ---------------------------------------------------------------------------


def test_song_dict_to_music_candidate_maps_artist_to_creator_and_id_to_str():
    song = {"id": 1, "title": "A", "artist": "Artist", "genre": "pop", "mood": "happy", "energy": 0.8, "tempo_bpm": 120, "valence": 0.5, "danceability": 0.8, "acousticness": 0.1}

    candidate = song_dict_to_music_candidate(song)

    assert candidate.candidate_id == "1"
    assert candidate.creator == "Artist"
    assert candidate.source == "legacy-dict"


def test_song_dict_to_music_candidate_missing_field_raises_key_error():
    song = {"id": 1, "title": "A", "artist": "Artist", "genre": "pop", "mood": "happy", "energy": 0.8}

    with pytest.raises(KeyError):
        song_dict_to_music_candidate(song)


# ---------------------------------------------------------------------------
# Full-catalog regression: legacy output must match the documented baseline
# ---------------------------------------------------------------------------


def test_full_catalog_top_five_matches_documented_baseline():
    songs = load_songs("data/songs.csv")
    recommendations = recommend_songs(DEFAULT_LEGACY_PROFILE, songs, k=5)

    actual = [
        (item["song"]["title"], item["song"]["artist"], round(item["score"], 2))
        for item in recommendations
    ]

    assert actual == EXPECTED_TOP_FIVE


def test_cli_still_produces_documented_baseline(capsys):
    main_module.main()

    output = capsys.readouterr().out
    assert "Loaded songs: 20" in output
    for title, artist, score in EXPECTED_TOP_FIVE:
        assert f"{title} — {artist}" in output
        assert f"Score: {score:.2f}/10" in output


# ---------------------------------------------------------------------------
# Legacy vs. canonical equivalence across the full catalog
# ---------------------------------------------------------------------------


def test_legacy_and_canonical_outputs_are_identical_for_full_catalog():
    legacy_songs = load_songs("data/songs.csv")
    legacy_results = recommend_songs(DEFAULT_LEGACY_PROFILE, legacy_songs, k=len(legacy_songs))

    candidates = load_music_candidates("data/songs.csv")
    profile = legacy_profile_to_user_profile(DEFAULT_LEGACY_PROFILE)
    canonical_results = recommend_music(candidates, profile, limit=len(candidates))

    assert len(legacy_results) == len(canonical_results)
    for legacy_item, canonical_item in zip(legacy_results, canonical_results):
        assert legacy_item["song"]["title"] == canonical_item.candidate.title
        assert legacy_item["song"]["artist"] == canonical_item.candidate.creator
        assert legacy_item["score"] == pytest.approx(canonical_item.score_breakdown.total_score)
        assert legacy_item["reasons"] == [component.reason for component in canonical_item.score_breakdown.components]
