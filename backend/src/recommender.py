from typing import List, Dict, Tuple
from dataclasses import dataclass

from src.intentune.domain.models import MusicCandidate, UserProfile as CanonicalUserProfile
from src.intentune.domain.scoring import (
    score_candidate,
    GENRE_WEIGHT,
    MOOD_WEIGHT,
    ENERGY_WEIGHT,
    DANCEABILITY_WEIGHT,
    MAX_SCORE,
)
from src.intentune.domain.ranking import rank_candidates
from src.intentune.adapters.csv_catalog import load_music_candidates

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


# ---------------------------------------------------------------------------
# Legacy <-> canonical boundary conversions.
#
# Direction: legacy input -> converter -> canonical domain flow -> converter
# -> legacy output. The canonical scorer/ranker in src/intentune/domain/ is
# the single source of truth; score_song() and recommend_songs() below no
# longer contain their own copy of the scoring math.
# ---------------------------------------------------------------------------

_REQUIRED_LEGACY_PROFILE_KEYS = ("favorite_genre", "favorite_mood", "preferred_energy", "preferred_danceability")
_REQUIRED_LEGACY_SONG_FIELDS = ("genre", "mood", "energy", "danceability")
_PLACEHOLDER_SCORE_SONG_IDENTITY = "legacy-score-song"


def legacy_profile_to_user_profile(user_prefs: Dict) -> CanonicalUserProfile:
    """Convert a legacy dictionary profile into a canonical UserProfile.

    ListeningContext and FeatureWeights are not populated here -- the legacy
    dictionary profile has no session-context or per-feature-weight concept
    yet. They remain future inputs (see docs/planning/development-phases.md).
    """
    for key in _REQUIRED_LEGACY_PROFILE_KEYS:
        if key not in user_prefs:
            raise KeyError(f"Missing user preference: {key}")

    return CanonicalUserProfile(
        preferred_genres=(str(user_prefs["favorite_genre"]),),
        preferred_moods=(str(user_prefs["favorite_mood"]),),
        preferred_energy=user_prefs["preferred_energy"],
        preferred_danceability=user_prefs["preferred_danceability"],
    )


def song_dict_to_music_candidate(song: Dict) -> MusicCandidate:
    """Convert a full legacy song dictionary (as returned by load_songs()) into a MusicCandidate."""
    for key in _REQUIRED_LEGACY_SONG_FIELDS:
        if key not in song:
            raise KeyError(f"Missing song field: {key}")

    return MusicCandidate(
        candidate_id=str(song["id"]),
        title=str(song["title"]),
        creator=str(song["artist"]),
        source="legacy-dict",
        genre=song["genre"],
        mood=song["mood"],
        energy=song["energy"],
        danceability=song["danceability"],
        tempo_bpm=song.get("tempo_bpm"),
        valence=song.get("valence"),
        acousticness=song.get("acousticness"),
    )


def _score_fields_to_music_candidate(song: Dict) -> MusicCandidate:
    """Convert score_song()'s narrower 4-field song dict into a MusicCandidate.

    score_song() never receives an id, title, or artist -- only the four
    scoring fields -- so a fixed placeholder identity is used. It is never
    exposed to callers of score_song().
    """
    for key in _REQUIRED_LEGACY_SONG_FIELDS:
        if key not in song:
            raise KeyError(f"Missing song field: {key}")

    return MusicCandidate(
        candidate_id=_PLACEHOLDER_SCORE_SONG_IDENTITY,
        title=_PLACEHOLDER_SCORE_SONG_IDENTITY,
        creator=_PLACEHOLDER_SCORE_SONG_IDENTITY,
        source="legacy-dict",
        genre=song["genre"],
        mood=song["mood"],
        energy=song["energy"],
        danceability=song["danceability"],
    )


def _candidate_to_song_dict(candidate: MusicCandidate) -> Dict:
    """Convert a CSV-sourced MusicCandidate back into the historical song dict shape."""
    return {
        "id": int(candidate.candidate_id),
        "title": candidate.title,
        "artist": candidate.creator,
        "genre": candidate.genre,
        "mood": candidate.mood,
        "energy": candidate.energy,
        "tempo_bpm": int(candidate.tempo_bpm),
        "valence": candidate.valence,
        "danceability": candidate.danceability,
        "acousticness": candidate.acousticness,
    }


def load_songs(csv_path: str) -> List[Dict]:
    """Load songs from a CSV file into a list of dictionaries.

    Delegates the actual CSV parsing to the canonical CSV adapter
    (src/intentune/adapters/csv_catalog.py) and converts the resulting
    MusicCandidate objects back into the historical dictionary shape, so
    there is only one implementation of CSV parsing in the codebase.
    """
    candidates = load_music_candidates(csv_path)
    songs = [_candidate_to_song_dict(candidate) for candidate in candidates]

    print(f"Loaded songs: {len(songs)}")
    return songs


def score_song(user_prefs: Dict, song: Dict) -> Tuple[float, List[str]]:
    """Score one song against a user profile and explain the result.

    Delegates to the canonical scorer (src/intentune/domain/scoring.py) after
    converting the legacy dict shapes into MusicCandidate/UserProfile.
    """
    profile = legacy_profile_to_user_profile(user_prefs)
    candidate = _score_fields_to_music_candidate(song)

    breakdown = score_candidate(candidate, profile)
    reasons = [component.reason for component in breakdown.components]
    return breakdown.total_score, reasons


def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5) -> List[Dict]:
    """Rank songs by the current content-based scoring rule and return the top k results.

    Delegates to canonical ranking (src/intentune/domain/ranking.py) after
    converting to MusicCandidate/UserProfile, then converts back to the
    historical {"song", "score", "reasons"} shape using the exact original
    song dict objects the caller passed in.
    """
    if not isinstance(k, int):
        raise TypeError("k must be an integer")
    if k < 0:
        raise ValueError("k cannot be negative")
    if k == 0:
        return []

    if not songs:
        return []

    profile = legacy_profile_to_user_profile(user_prefs)
    candidates = [song_dict_to_music_candidate(song) for song in songs]
    original_song_by_candidate_identity = {id(candidate): song for candidate, song in zip(candidates, songs)}

    recommendations = rank_candidates(candidates, profile, limit=k)

    return [
        {
            "song": original_song_by_candidate_identity[id(recommendation.candidate)],
            "score": recommendation.score_breakdown.total_score,
            "reasons": [component.reason for component in recommendation.score_breakdown.components],
        }
        for recommendation in recommendations
    ]
