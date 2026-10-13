import pytest

from src.intentune.domain.models import MusicCandidate, UserProfile
from src.intentune.application.recommendation_service import recommend_from_catalog, recommend_music


def _profile():
    return UserProfile(preferred_genres=("pop",), preferred_moods=("happy",), preferred_energy=0.8, preferred_danceability=0.8)


def _candidates():
    return [
        MusicCandidate(candidate_id="1", title="Low Match", creator="A", source="csv", genre="rock", mood="sad", energy=0.1, danceability=0.1),
        MusicCandidate(candidate_id="2", title="High Match", creator="B", source="csv", genre="pop", mood="happy", energy=0.8, danceability=0.8),
    ]


def test_recommend_music_returns_ranked_typed_recommendations():
    recommendations = recommend_music(_candidates(), _profile(), limit=2)

    assert len(recommendations) == 2
    assert recommendations[0].candidate.title == "High Match"
    assert recommendations[0].rank == 1
    assert recommendations[1].rank == 2


def test_recommend_music_default_limit_is_five():
    candidates = [
        MusicCandidate(candidate_id=str(i), title=f"Song {i}", creator="Artist", source="csv", genre="pop", mood="happy", energy=0.8, danceability=0.8)
        for i in range(10)
    ]

    recommendations = recommend_music(candidates, _profile())

    assert len(recommendations) == 5


def test_recommend_music_rejects_non_user_profile():
    with pytest.raises(TypeError):
        recommend_music(_candidates(), {"favorite_genre": "pop"}, limit=2)


def test_recommend_music_rejects_non_music_candidate_items():
    with pytest.raises(TypeError):
        recommend_music([{"title": "not a candidate"}], _profile(), limit=2)


def test_recommend_music_handles_empty_candidates():
    assert recommend_music([], _profile(), limit=5) == []


class _FakeCatalog:
    def __init__(self, candidates):
        self._candidates = candidates

    def list_candidates(self):
        return self._candidates


def test_recommend_from_catalog_ranks_candidates_from_fake_catalog():
    catalog = _FakeCatalog(_candidates())

    recommendations = recommend_from_catalog(catalog, _profile(), limit=2)

    assert len(recommendations) == 2
    assert recommendations[0].candidate.title == "High Match"
    assert recommendations[0].rank == 1


def test_recommend_from_catalog_is_deterministic():
    catalog = _FakeCatalog(_candidates())

    first = recommend_from_catalog(catalog, _profile(), limit=2)
    second = recommend_from_catalog(catalog, _profile(), limit=2)

    assert [r.candidate.candidate_id for r in first] == [r.candidate.candidate_id for r in second]


def test_recommend_from_catalog_respects_limit():
    candidates = [
        MusicCandidate(candidate_id=str(i), title=f"Song {i}", creator="Artist", source="fake", genre="pop", mood="happy", energy=0.8, danceability=0.8)
        for i in range(10)
    ]
    catalog = _FakeCatalog(candidates)

    recommendations = recommend_from_catalog(catalog, _profile(), limit=3)

    assert len(recommendations) == 3


def test_recommend_from_catalog_handles_empty_catalog():
    catalog = _FakeCatalog([])

    assert recommend_from_catalog(catalog, _profile(), limit=5) == []


def test_recommend_from_catalog_rejects_non_catalog():
    with pytest.raises(TypeError):
        recommend_from_catalog(object(), _profile(), limit=5)


def test_recommend_from_catalog_rejects_non_user_profile():
    catalog = _FakeCatalog(_candidates())

    with pytest.raises(TypeError):
        recommend_from_catalog(catalog, {"favorite_genre": "pop"}, limit=2)
