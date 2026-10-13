import csv

import pytest

from src import main as main_module
from src.recommender import (
    Song,
    UserProfile,
    Recommender,
    load_songs,
    recommend_songs,
    score_song,
)


def make_small_recommender() -> Recommender:
    songs = [
        Song(
            id=1,
            title="Test Pop Track",
            artist="Test Artist",
            genre="pop",
            mood="happy",
            energy=0.8,
            tempo_bpm=120,
            valence=0.9,
            danceability=0.8,
            acousticness=0.2,
        ),
        Song(
            id=2,
            title="Chill Lofi Loop",
            artist="Test Artist",
            genre="lofi",
            mood="chill",
            energy=0.4,
            tempo_bpm=80,
            valence=0.6,
            danceability=0.5,
            acousticness=0.9,
        ),
    ]
    return Recommender(songs)


def test_recommend_returns_songs_sorted_by_score():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    results = rec.recommend(user, k=2)

    assert len(results) == 2
    assert results[0].genre == "pop"
    assert results[0].mood == "happy"


def test_explain_recommendation_returns_non_empty_string():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    song = rec.songs[0]

    explanation = rec.explain_recommendation(user, song)
    assert isinstance(explanation, str)
    assert explanation.strip() != ""


def test_load_songs_returns_list_of_dicts():
    songs = load_songs("data/songs.csv")

    assert isinstance(songs, list)
    assert songs
    assert all(isinstance(song, dict) for song in songs)


def test_load_songs_converts_types_and_preserves_strings():
    songs = load_songs("data/songs.csv")
    first_song = songs[0]

    assert isinstance(first_song["id"], int)
    assert isinstance(first_song["tempo_bpm"], int)
    assert isinstance(first_song["energy"], float)
    assert isinstance(first_song["valence"], float)
    assert isinstance(first_song["danceability"], float)
    assert isinstance(first_song["acousticness"], float)
    assert isinstance(first_song["title"], str)
    assert isinstance(first_song["artist"], str)
    assert isinstance(first_song["genre"], str)
    assert isinstance(first_song["mood"], str)


def test_load_songs_reads_expected_catalog_size():
    songs = load_songs("data/songs.csv")

    assert len(songs) == 20


def test_load_songs_uses_optional_path_for_temp_csv(tmp_path):
    csv_path = tmp_path / "songs.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "title", "artist", "genre", "mood", "energy", "tempo_bpm", "valence", "danceability", "acousticness"])
        writer.writeheader()
        writer.writerow({
            "id": "1",
            "title": "  Test Song  ",
            "artist": " Artist ",
            "genre": " pop ",
            "mood": " happy ",
            "energy": "0.80",
            "tempo_bpm": "120",
            "valence": "0.90",
            "danceability": "0.70",
            "acousticness": "0.20",
        })

    songs = load_songs(str(csv_path))

    assert len(songs) == 1
    assert songs[0]["title"] == "Test Song"
    assert songs[0]["artist"] == "Artist"
    assert songs[0]["genre"] == "pop"
    assert songs[0]["mood"] == "happy"
    assert songs[0]["id"] == 1
    assert songs[0]["tempo_bpm"] == 120
    assert songs[0]["energy"] == 0.8


def test_load_songs_raises_for_invalid_numeric_value(tmp_path):
    csv_path = tmp_path / "bad.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "title", "artist", "genre", "mood", "energy", "tempo_bpm", "valence", "danceability", "acousticness"])
        writer.writeheader()
        writer.writerow({
            "id": "1",
            "title": "Bad Song",
            "artist": "Artist",
            "genre": "pop",
            "mood": "happy",
            "energy": "not-a-float",
            "tempo_bpm": "120",
            "valence": "0.90",
            "danceability": "0.70",
            "acousticness": "0.20",
        })

    with pytest.raises(ValueError):
        load_songs(str(csv_path))


def test_load_songs_raises_for_missing_file(tmp_path):
    missing_path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError):
        load_songs(str(missing_path))


@pytest.mark.parametrize(
    ("user_prefs", "song", "expected_score"),
    [
        ({"favorite_genre": "lofi", "favorite_mood": "focused", "preferred_energy": 0.40, "preferred_danceability": 0.30}, {"genre": "lofi", "mood": "focused", "energy": 0.40, "danceability": 0.30}, 10.0),
        ({"favorite_genre": "lofi", "favorite_mood": "focused", "preferred_energy": 0.40, "preferred_danceability": 0.30}, {"genre": "pop", "mood": "focused", "energy": 0.40, "danceability": 0.30}, 7.0),
        ({"favorite_genre": "lofi", "favorite_mood": "focused", "preferred_energy": 0.40, "preferred_danceability": 0.30}, {"genre": "lofi", "mood": "chill", "energy": 0.40, "danceability": 0.30}, 7.0),
        ({"favorite_genre": "lofi", "favorite_mood": "focused", "preferred_energy": 0.40, "preferred_danceability": 0.30}, {"genre": "pop", "mood": "chill", "energy": 0.90, "danceability": 0.90}, 0.0),
    ],
)
def test_score_song_returns_expected_scores(user_prefs, song, expected_score):
    score, reasons = score_song(user_prefs, song)

    assert score == pytest.approx(expected_score)
    assert isinstance(reasons, list)
    assert reasons


def test_score_song_is_case_insensitive_for_genre_and_mood():
    user_prefs = {
        "favorite_genre": "Lofi",
        "favorite_mood": "Focused",
        "preferred_energy": 0.40,
        "preferred_danceability": 0.30,
    }
    song = {"genre": "lofi", "mood": "focused", "energy": 0.40, "danceability": 0.30}

    score, reasons = score_song(user_prefs, song)

    assert score == pytest.approx(10.0)
    assert any("genre match" in reason for reason in reasons)
    assert any("mood match" in reason for reason in reasons)


def test_score_song_rewards_closeness_not_larger_values():
    user_prefs = {
        "favorite_genre": "lofi",
        "favorite_mood": "focused",
        "preferred_energy": 0.20,
        "preferred_danceability": 0.20,
    }
    close_song = {"genre": "lofi", "mood": "focused", "energy": 0.20, "danceability": 0.20}
    far_song = {"genre": "lofi", "mood": "focused", "energy": 0.90, "danceability": 0.90}

    close_score, _ = score_song(user_prefs, close_song)
    far_score, _ = score_song(user_prefs, far_song)

    assert close_score > far_score


def test_score_song_rejects_out_of_range_values():
    user_prefs = {
        "favorite_genre": "lofi",
        "favorite_mood": "focused",
        "preferred_energy": -0.1,
        "preferred_danceability": 0.30,
    }
    song = {"genre": "lofi", "mood": "focused", "energy": 0.40, "danceability": 0.30}

    with pytest.raises(ValueError):
        score_song(user_prefs, song)


def test_score_song_raises_for_missing_required_keys():
    user_prefs = {
        "favorite_genre": "lofi",
        "favorite_mood": "focused",
        "preferred_energy": 0.40,
        "preferred_danceability": 0.30,
    }
    song = {"genre": "lofi", "mood": "focused", "energy": 0.40}

    with pytest.raises((KeyError, ValueError)):
        score_song(user_prefs, song)


def test_recommend_songs_returns_ranked_results_and_does_not_mutate():
    user_prefs = {
        "favorite_genre": "lofi",
        "favorite_mood": "focused",
        "preferred_energy": 0.40,
        "preferred_danceability": 0.30,
    }
    songs = [
        {"id": 1, "title": "A", "artist": "Artist", "genre": "lofi", "mood": "focused", "energy": 0.40, "tempo_bpm": 80, "valence": 0.5, "danceability": 0.30, "acousticness": 0.2},
        {"id": 2, "title": "B", "artist": "Artist", "genre": "pop", "mood": "chill", "energy": 0.90, "tempo_bpm": 120, "valence": 0.5, "danceability": 0.90, "acousticness": 0.8},
    ]
    original_titles = [song["title"] for song in songs]

    recommendations = recommend_songs(user_prefs, songs, k=2)

    assert len(recommendations) == 2
    assert recommendations[0]["score"] >= recommendations[1]["score"]
    assert [item["song"]["title"] for item in recommendations] == ["A", "B"]
    assert [song["title"] for song in songs] == original_titles


def test_recommend_songs_handles_edge_cases():
    user_prefs = {
        "favorite_genre": "lofi",
        "favorite_mood": "focused",
        "preferred_energy": 0.40,
        "preferred_danceability": 0.30,
    }

    assert recommend_songs(user_prefs, [], k=2) == []
    assert recommend_songs(user_prefs, [{"id": 1, "title": "A", "artist": "Artist", "genre": "lofi", "mood": "focused", "energy": 0.40, "tempo_bpm": 80, "valence": 0.5, "danceability": 0.30, "acousticness": 0.2}], k=0) == []

    with pytest.raises(ValueError):
        recommend_songs(user_prefs, [{"id": 1, "title": "A", "artist": "Artist", "genre": "lofi", "mood": "focused", "energy": 0.40, "tempo_bpm": 80, "valence": 0.5, "danceability": 0.30, "acousticness": 0.2}], k=-1)

    with pytest.raises((TypeError, ValueError)):
        recommend_songs(user_prefs, [{"id": 1, "title": "A", "artist": "Artist", "genre": "lofi", "mood": "focused", "energy": 0.40, "tempo_bpm": 80, "valence": 0.5, "danceability": 0.30, "acousticness": 0.2}], k="2")


def test_recommend_songs_returns_main_ready_result_shape():
    user_prefs = {
        "favorite_genre": "lofi",
        "favorite_mood": "focused",
        "preferred_energy": 0.40,
        "preferred_danceability": 0.30,
    }
    songs = [
        {"id": 1, "title": "A", "artist": "Artist", "genre": "lofi", "mood": "focused", "energy": 0.40, "tempo_bpm": 80, "valence": 0.5, "danceability": 0.30, "acousticness": 0.2},
        {"id": 2, "title": "B", "artist": "Artist", "genre": "pop", "mood": "chill", "energy": 0.90, "tempo_bpm": 120, "valence": 0.5, "danceability": 0.90, "acousticness": 0.8},
    ]

    recommendations = recommend_songs(user_prefs, songs, k=2)

    assert len(recommendations) == 2
    first = recommendations[0]
    assert set(first.keys()) == {"song", "score", "reasons"}
    assert isinstance(first["song"], dict)
    assert isinstance(first["score"], (int, float))
    assert isinstance(first["reasons"], list)
    assert first["reasons"]
    assert all(isinstance(reason, str) for reason in first["reasons"])


def test_main_prints_recommendation_details_for_real_catalog(capsys):
    main_module.main()

    output = capsys.readouterr().out
    assert "Loaded songs: 20" in output
    assert "Top recommendations:" in output
    assert "Sunrise City" in output
    assert "Score:" in output
    assert "Reasons:" in output


def test_main_displays_scores_in_descending_order(capsys):
    main_module.main()

    output = capsys.readouterr().out
    score_lines = [line for line in output.splitlines() if "Score:" in line]
    scores = []
    for line in score_lines:
        score_text = line.split("Score:", 1)[1].split("/", 1)[0].strip()
        scores.append(float(score_text))

    assert scores == sorted(scores, reverse=True)
