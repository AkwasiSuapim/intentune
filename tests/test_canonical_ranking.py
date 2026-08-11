import pytest

from src.intentune.domain.models import MusicCandidate, UserProfile
from src.intentune.domain.ranking import rank_candidates


def _profile():
    return UserProfile(preferred_genres=("pop",), preferred_moods=("happy",), preferred_energy=0.8, preferred_danceability=0.8)


def _candidate(candidate_id, title, creator, **overrides):
    values = dict(
        candidate_id=candidate_id,
        title=title,
        creator=creator,
        source="csv",
        genre="pop",
        mood="happy",
        energy=0.8,
        danceability=0.8,
    )
    values.update(overrides)
    return MusicCandidate(**values)


def test_descending_score_order():
    candidates = [
        _candidate("1", "Low Match", "A", genre="rock", mood="sad"),
        _candidate("2", "High Match", "B"),
    ]

    recommendations = rank_candidates(candidates, _profile(), limit=2)

    assert recommendations[0].candidate.title == "High Match"
    assert recommendations[0].score_breakdown.total_score > recommendations[1].score_breakdown.total_score


def test_title_tie_breaking():
    candidates = [
        _candidate("1", "Zebra Song", "A"),
        _candidate("2", "Apple Song", "A"),
    ]

    recommendations = rank_candidates(candidates, _profile(), limit=2)

    assert [r.candidate.title for r in recommendations] == ["Apple Song", "Zebra Song"]


def test_creator_tie_breaking():
    candidates = [
        _candidate("1", "Same Title", "Zebra Artist"),
        _candidate("2", "Same Title", "Apple Artist"),
    ]

    recommendations = rank_candidates(candidates, _profile(), limit=2)

    assert [r.candidate.creator for r in recommendations] == ["Apple Artist", "Zebra Artist"]


def test_stable_ordering_when_everything_ties():
    candidates = [
        _candidate("1", "Same Title", "Same Artist"),
        _candidate("2", "Same Title", "Same Artist"),
        _candidate("3", "Same Title", "Same Artist"),
    ]

    recommendations = rank_candidates(candidates, _profile(), limit=3)

    assert [r.candidate.candidate_id for r in recommendations] == ["1", "2", "3"]


def test_rank_assignment_starts_at_one():
    candidates = [
        _candidate("1", "A Song", "A"),
        _candidate("2", "B Song", "B"),
        _candidate("3", "C Song", "C"),
    ]

    recommendations = rank_candidates(candidates, _profile(), limit=3)

    assert [r.rank for r in recommendations] == [1, 2, 3]


def test_empty_candidate_list_returns_empty():
    assert rank_candidates([], _profile(), limit=5) == []


def test_zero_limit_returns_empty():
    candidates = [_candidate("1", "A Song", "A")]

    assert rank_candidates(candidates, _profile(), limit=0) == []


def test_negative_limit_raises_value_error():
    candidates = [_candidate("1", "A Song", "A")]

    with pytest.raises(ValueError):
        rank_candidates(candidates, _profile(), limit=-1)


def test_non_integer_limit_raises_type_error():
    candidates = [_candidate("1", "A Song", "A")]

    with pytest.raises(TypeError):
        rank_candidates(candidates, _profile(), limit="2")


def test_limit_larger_than_catalog_returns_all_candidates():
    candidates = [
        _candidate("1", "A Song", "A"),
        _candidate("2", "B Song", "B"),
    ]

    recommendations = rank_candidates(candidates, _profile(), limit=50)

    assert len(recommendations) == 2
    assert [r.rank for r in recommendations] == [1, 2]
