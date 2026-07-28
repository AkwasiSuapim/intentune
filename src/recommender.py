import csv
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

GENRE_WEIGHT = 3.0
MOOD_WEIGHT = 3.0
ENERGY_WEIGHT = 2.0
DANCEABILITY_WEIGHT = 2.0
MAX_SCORE = 10.0

@dataclass
class Song:
    """
    Represents a song and its attributes.
    Required by tests/test_recommender.py
    """
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float

@dataclass
class UserProfile:
    """
    Represents a user's taste preferences.
    Required by tests/test_recommender.py

    preferred_danceability defaults to 0.5, the value the Recommender wrapper
    used to hard-code regardless of the caller's intent. The default keeps
    old call sites (which never set this field) scoring exactly as before;
    passing an explicit value now actually reaches the scoring engine instead
    of being silently discarded.

    likes_acoustic is deprecated: it is accepted for backward compatibility
    with existing call sites only and has no effect on scoring or ranking.
    """
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool
    preferred_danceability: float = 0.5

class Recommender:
    """
    OOP implementation of the recommendation logic.
    Required by tests/test_recommender.py
    """
    def __init__(self, songs: List[Song]):
        self.songs = songs
        self._songs_by_id = {song.id: song for song in songs}
        self._song_dicts = [self._to_song_dict(song) for song in songs]
        self.last_recommendations: List[Dict] = []

    @staticmethod
    def _to_song_dict(song: Song) -> Dict:
        return {
            "id": song.id,
            "title": song.title,
            "artist": song.artist,
            "genre": song.genre,
            "mood": song.mood,
            "energy": song.energy,
            "tempo_bpm": int(song.tempo_bpm),
            "valence": song.valence,
            "danceability": song.danceability,
            "acousticness": song.acousticness,
        }

    @staticmethod
    def _to_user_prefs(user: UserProfile) -> Dict:
        return {
            "favorite_genre": user.favorite_genre,
            "favorite_mood": user.favorite_mood,
            "preferred_energy": user.target_energy,
            "preferred_danceability": user.preferred_danceability,
        }

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        recommendations = recommend_songs(
            self._to_user_prefs(user),
            self._song_dicts,
            k=k,
        )
        self.last_recommendations = recommendations
        return [self._songs_by_id[recommendation["song"]["id"]] for recommendation in recommendations]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        score, reasons = score_song(
            self._to_user_prefs(user),
            {
                "genre": song.genre,
                "mood": song.mood,
                "energy": song.energy,
                "danceability": song.danceability,
            },
        )
        return " | ".join(reasons)

def load_songs(csv_path: str) -> List[Dict]:
    """Load songs from a CSV file into a list of dictionaries."""
    csv_file = Path(csv_path)
    if not csv_file.is_absolute():
        csv_file = Path(__file__).resolve().parent.parent / csv_file

    with csv_file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        songs = []
        for row in reader:
            song = {
                "id": int(row["id"].strip()),
                "title": row["title"].strip(),
                "artist": row["artist"].strip(),
                "genre": row["genre"].strip(),
                "mood": row["mood"].strip(),
                "energy": float(row["energy"].strip()),
                "tempo_bpm": int(row["tempo_bpm"].strip()),
                "valence": float(row["valence"].strip()),
                "danceability": float(row["danceability"].strip()),
                "acousticness": float(row["acousticness"].strip()),
            }
            songs.append(song)

    print(f"Loaded songs: {len(songs)}")
    return songs

def _validate_numeric_preference(value: float, field_name: str) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")
    return float(value)


def _calculate_similarity_points(preferred_value: float, actual_value: float, weight: float) -> Tuple[float, str]:
    difference = abs(actual_value - preferred_value)
    if difference >= 0.5:
        similarity = 0.0
    else:
        similarity = 1.0 - difference
    similarity = max(0.0, min(1.0, similarity))
    points = similarity * weight
    return points, f"similarity ({points:.2f})"


def score_song(user_prefs: Dict, song: Dict) -> Tuple[float, List[str]]:
    """Score one song against a user profile and explain the result."""
    required_user_keys = ["favorite_genre", "favorite_mood", "preferred_energy", "preferred_danceability"]
    required_song_keys = ["genre", "mood", "energy", "danceability"]

    for key in required_user_keys:
        if key not in user_prefs:
            raise KeyError(f"Missing user preference: {key}")
    for key in required_song_keys:
        if key not in song:
            raise KeyError(f"Missing song field: {key}")

    preferred_energy = _validate_numeric_preference(user_prefs["preferred_energy"], "preferred_energy")
    preferred_danceability = _validate_numeric_preference(user_prefs["preferred_danceability"], "preferred_danceability")
    song_energy = _validate_numeric_preference(song["energy"], "song energy")
    song_danceability = _validate_numeric_preference(song["danceability"], "song danceability")

    favorite_genre = str(user_prefs["favorite_genre"]).strip().lower()
    favorite_mood = str(user_prefs["favorite_mood"]).strip().lower()
    song_genre = str(song["genre"]).strip().lower()
    song_mood = str(song["mood"]).strip().lower()

    reasons: List[str] = []
    score = 0.0

    if song_genre == favorite_genre:
        score += GENRE_WEIGHT
        reasons.append(f"genre match (+{GENRE_WEIGHT:.1f})")
    else:
        reasons.append("genre did not match (+0.0)")

    if song_mood == favorite_mood:
        score += MOOD_WEIGHT
        reasons.append(f"mood match (+{MOOD_WEIGHT:.1f})")
    else:
        reasons.append("mood did not match (+0.0)")

    energy_points, energy_reason = _calculate_similarity_points(preferred_energy, song_energy, ENERGY_WEIGHT)
    score += energy_points
    reasons.append(f"energy similarity (+{energy_points:.2f})")

    danceability_points, danceability_reason = _calculate_similarity_points(preferred_danceability, song_danceability, DANCEABILITY_WEIGHT)
    score += danceability_points
    reasons.append(f"danceability similarity (+{danceability_points:.2f})")

    if score > MAX_SCORE:
        score = MAX_SCORE

    if score < 0.0:
        score = 0.0

    return round(score, 6), reasons


def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5) -> List[Dict]:
    """Rank songs by a simple content-based scoring rule and return the top k results."""
    if not isinstance(k, int):
        raise TypeError("k must be an integer")
    if k < 0:
        raise ValueError("k cannot be negative")
    if k == 0:
        return []

    if not songs:
        return []

    recommendations = []
    for song in songs:
        score, reasons = score_song(user_prefs, song)
        explanation = " | ".join(reasons)
        recommendations.append({
            "song": song,
            "score": score,
            "reasons": reasons,
        })

    ranked_recommendations = sorted(
        recommendations,
        key=lambda item: (-item["score"], str(item["song"]["title"]).lower(), str(item["song"]["artist"]).lower()),
    )

    top_recommendations = ranked_recommendations[:k]
    return [
        {
            "song": item["song"],
            "score": item["score"],
            "reasons": item["reasons"],
        }
        for item in top_recommendations
    ]
