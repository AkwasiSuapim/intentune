import pytest

from src.intentune.adapters.csv_catalog import CsvCatalog, load_music_candidates, music_candidate_from_csv_row
from src.intentune.ports.catalog import Catalog


def _sample_row(**overrides):
    row = {
        "id": "1",
        "title": "Sunrise City",
        "artist": "Neon Echo",
        "genre": "pop",
        "mood": "happy",
        "energy": "0.82",
        "tempo_bpm": "118",
        "valence": "0.91",
        "danceability": "0.77",
        "acousticness": "0.08",
    }
    row.update(overrides)
    return row


def test_valid_csv_row_conversion():
    candidate = music_candidate_from_csv_row(_sample_row())

    assert candidate.candidate_id == "1"
    assert candidate.title == "Sunrise City"
    assert candidate.genre == "pop"
    assert candidate.mood == "happy"


def test_correct_numeric_conversion():
    candidate = music_candidate_from_csv_row(_sample_row())

    assert candidate.energy == pytest.approx(0.82)
    assert candidate.tempo_bpm == pytest.approx(118)
    assert candidate.valence == pytest.approx(0.91)
    assert candidate.danceability == pytest.approx(0.77)
    assert candidate.acousticness == pytest.approx(0.08)


def test_artist_maps_to_creator():
    candidate = music_candidate_from_csv_row(_sample_row(artist="Neon Echo"))

    assert candidate.creator == "Neon Echo"


def test_source_set_to_csv():
    candidate = music_candidate_from_csv_row(_sample_row())

    assert candidate.source == "csv"


def test_missing_required_column_raises():
    row = _sample_row()
    del row["artist"]

    with pytest.raises(ValueError):
        music_candidate_from_csv_row(row)


def test_malformed_number_raises():
    with pytest.raises(ValueError):
        music_candidate_from_csv_row(_sample_row(energy="not-a-float"))


def test_blank_required_value_raises():
    with pytest.raises(ValueError):
        music_candidate_from_csv_row(_sample_row(title="   "))


def test_optional_values_where_supported():
    row = _sample_row()
    del row["genre"]
    row["mood"] = ""
    row["acousticness"] = ""

    candidate = music_candidate_from_csv_row(row)

    assert candidate.genre is None
    assert candidate.mood is None
    assert candidate.acousticness is None
    assert candidate.title == "Sunrise City"


def test_load_music_candidates_reads_full_catalog():
    candidates = load_music_candidates("data/songs.csv")

    assert len(candidates) == 20
    assert all(candidate.source == "csv" for candidate in candidates)
    assert candidates[0].title == "Sunrise City"


def test_load_music_candidates_does_not_print(capsys):
    load_music_candidates("data/songs.csv")

    output = capsys.readouterr().out
    assert output == ""


def test_csv_catalog_satisfies_catalog_protocol():
    assert isinstance(CsvCatalog("data/songs.csv"), Catalog)


def test_csv_catalog_list_candidates_reads_full_catalog():
    catalog = CsvCatalog("data/songs.csv")

    candidates = catalog.list_candidates()

    assert len(candidates) == 20
    assert all(candidate.source == "csv" for candidate in candidates)


def test_csv_catalog_does_not_print(capsys):
    CsvCatalog("data/songs.csv").list_candidates()

    output = capsys.readouterr().out
    assert output == ""
