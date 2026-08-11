"""CSV catalog adapter: converts raw CSV rows into canonical MusicCandidate objects.

This is the only module that knows about the CSV column names, file paths,
and string-to-number conversion for the song catalog. The domain layer
(src/intentune/domain/) has no knowledge of CSV at all -- see
docs/architecture.md.

`id`, `title`, and `artist` are the only columns this adapter treats as
strictly required, matching MusicCandidate's own required fields. Genre,
mood, and the audio features are treated as optional columns: a missing
column or a blank cell becomes None on the resulting MusicCandidate rather
than an error, since future non-CSV providers (and, in principle, future CSV
variants) may not always supply them. A non-blank value that fails to parse
as a number is reported clearly, naming the offending row.

This adapter does not print anything -- src.recommender.load_songs() decides
what to report to the caller, preserving the historical "Loaded songs: N"
CLI message at that boundary instead of here.
"""

import csv
from pathlib import Path
from typing import Dict, List, Optional

from src.intentune.domain.models import MusicCandidate

_REQUIRED_COLUMNS = ("id", "title", "artist")
_OPTIONAL_TEXT_COLUMNS = ("genre", "mood")
_OPTIONAL_NUMERIC_COLUMNS = (
    ("energy", float),
    ("tempo_bpm", int),
    ("valence", float),
    ("danceability", float),
    ("acousticness", float),
)


def _parse_optional_text(row: Dict, column: str) -> Optional[str]:
    value = row.get(column)
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_optional_number(row: Dict, column: str, caster, row_id: str):
    raw_value = row.get(column)
    if raw_value is None:
        return None
    cleaned = raw_value.strip()
    if not cleaned:
        return None
    try:
        return caster(cleaned)
    except ValueError as error:
        raise ValueError(f"CSV row {row_id!r} has a malformed {column!r} value: {cleaned!r}") from error


def music_candidate_from_csv_row(row: Dict) -> MusicCandidate:
    """Convert one raw CSV row (string values, as returned by csv.DictReader) into a MusicCandidate."""
    missing = [column for column in _REQUIRED_COLUMNS if column not in row]
    if missing:
        raise ValueError(f"CSV row is missing required column(s): {', '.join(missing)}")

    row_id = row["id"].strip()
    title = row["title"].strip()
    artist = row["artist"].strip()

    numeric_values = {
        column: _parse_optional_number(row, column, caster, row_id)
        for column, caster in _OPTIONAL_NUMERIC_COLUMNS
    }

    return MusicCandidate(
        candidate_id=row_id,
        title=title,
        creator=artist,
        source="csv",
        genre=_parse_optional_text(row, "genre"),
        mood=_parse_optional_text(row, "mood"),
        energy=numeric_values["energy"],
        danceability=numeric_values["danceability"],
        tempo_bpm=numeric_values["tempo_bpm"],
        valence=numeric_values["valence"],
        acousticness=numeric_values["acousticness"],
    )


def load_music_candidates(csv_path: str) -> List[MusicCandidate]:
    """Read a CSV catalog file and return canonical MusicCandidate objects.

    A relative path is resolved against the repository root, matching the
    historical behavior of src.recommender.load_songs().
    """
    csv_file = Path(csv_path)
    if not csv_file.is_absolute():
        csv_file = Path(__file__).resolve().parents[3] / csv_path

    with csv_file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [music_candidate_from_csv_row(row) for row in reader]
