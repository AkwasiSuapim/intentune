from src.intentune.domain.models import MusicCandidate
from src.intentune.ports.catalog import Catalog


class _FakeCatalog:
    def __init__(self, candidates):
        self._candidates = candidates

    def list_candidates(self):
        return self._candidates


def test_object_with_list_candidates_satisfies_catalog_protocol():
    fake = _FakeCatalog([])

    assert isinstance(fake, Catalog)


def test_object_without_list_candidates_does_not_satisfy_catalog_protocol():
    class NotACatalog:
        pass

    assert not isinstance(NotACatalog(), Catalog)


def test_fake_catalog_returns_music_candidates():
    candidate = MusicCandidate(candidate_id="1", title="Song", creator="Artist", source="fake")
    fake = _FakeCatalog([candidate])

    result = fake.list_candidates()

    assert result == [candidate]
