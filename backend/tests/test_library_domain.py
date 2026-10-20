"""Library domain rules: formats, safe relative paths, tag interpretation, and entity invariants."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.intentune.application.library import LibraryPolicy
from src.intentune.domain.library import (
    EMBEDDED_TAGS_SOURCE,
    AudioFormat,
    AudioProbe,
    DiscoveredFile,
    EmbeddedTags,
    FailureReason,
    LabelKind,
    LibrarySource,
    SourceFile,
    SourceFileStatus,
    SourceStatus,
    Track,
    TrackLabel,
    TrackStatus,
    new_library_source,
    require_relative_path,
    split_genres,
    year_from_tag,
)

_NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
_ID = "3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e"
_OTHER_ID = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"
_SHA = "a" * 64


def _track(**overrides):
    values = dict(
        track_id=_ID,
        sha256=_SHA,
        size_bytes=1000,
        audio_format=AudioFormat.MP3,
        status=TrackStatus.IMPORTED,
        original_filename="song.mp3",
        created_at=_NOW,
        updated_at=_NOW,
    )
    values.update(overrides)
    return Track(**values)


def _source_file(**overrides):
    values = dict(
        source_file_id=_ID,
        source_id=_OTHER_ID,
        relative_path="album/song.mp3",
        size_bytes=1000,
        modified_ns=5,
        status=SourceFileStatus.IMPORTED,
        created_at=_NOW,
        updated_at=_NOW,
        sha256=_SHA,
        track_id=_OTHER_ID,
    )
    values.update(overrides)
    return SourceFile(**values)


# --- Formats ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("song.mp3", AudioFormat.MP3),
        ("SONG.MP3", AudioFormat.MP3),
        ("a/b/track.flac", AudioFormat.FLAC),
        ("archive.tar.ogg", AudioFormat.OGG),
        ("voice.opus", AudioFormat.OPUS),
        ("tune.m4a", AudioFormat.M4A),
        ("take.wav", AudioFormat.WAV),
    ],
)
def test_allowlisted_extensions_map_to_formats(filename, expected):
    assert AudioFormat.from_filename(filename) is expected


@pytest.mark.parametrize("filename", ["cover.jpg", "notes.txt", "song.wma", "song.aiff", "song.mp3.txt", "noextension", ".mp3", "dir.mp3/file"])
def test_other_files_are_not_audio(filename):
    assert AudioFormat.from_filename(filename) is None


def test_format_value_is_the_managed_extension():
    assert {audio_format.extension for audio_format in AudioFormat} == {"mp3", "m4a", "flac", "ogg", "opus", "wav"}


# --- Relative paths -----------------------------------------------------------------


@pytest.mark.parametrize("path", ["song.mp3", "Artist/Album/01 Song.mp3", "a b/c.flac"])
def test_safe_relative_paths_are_accepted(path):
    assert require_relative_path(path) == path


@pytest.mark.parametrize(
    "path",
    ["", "/abs/song.mp3", "C:/music/song.mp3", "c:song.mp3", "a\\b.mp3", "../song.mp3", "a/../b.mp3", "a//b.mp3", "./a.mp3", "a/", "a\x00.mp3", None],
)
def test_unsafe_relative_paths_are_rejected(path):
    with pytest.raises(ValueError):
        require_relative_path(path)


def test_discovered_file_derives_filename_and_format():
    discovered = DiscoveredFile(relative_path="Artist/Album/01 Song.FLAC", size_bytes=10, modified_ns=1)

    assert discovered.filename == "01 Song.FLAC"
    assert discovered.audio_format is AudioFormat.FLAC


@pytest.mark.parametrize("field, value", [("size_bytes", -1), ("modified_ns", -1), ("size_bytes", 1.5), ("relative_path", "../x.mp3")])
def test_discovered_file_rejects_invalid_values(field, value):
    values = dict(relative_path="a.mp3", size_bytes=1, modified_ns=1)
    values[field] = value
    with pytest.raises(ValueError):
        DiscoveredFile(**values)


# --- Tag interpretation ---------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [("2019", 2019), ("2019-05-03", 2019), (" 2001 ", 2001), ("1999-12-31T23:59:59", 1999), ("0000", None), ("99", None), ("May 2019", None), ("", None)],
)
def test_year_comes_only_from_a_leading_four_digit_year(value, expected):
    assert year_from_tag(value) == expected


def test_genres_split_on_semicolons_and_drop_duplicates():
    assert split_genres(["Rock; Indie", "rock", "  Pop  ", "", "Hip-Hop/Rap", "Drum & Bass"]) == (
        "Rock",
        "Indie",
        "Pop",
        "Hip-Hop/Rap",
        "Drum & Bass",
    )


def test_embedded_tags_from_tag_values():
    tags = EmbeddedTags.from_tag_values(
        titles=["", "  Title  ", "Ignored"],
        artists=["A", " B ", "A"],
        albums=["Album"],
        dates=["unknown", "2019-05-03"],
        genres=["Jazz; Blues"],
    )

    assert tags == EmbeddedTags(title="Title", artist="A, B", album="Album", year=2019, genres=("Jazz", "Blues"))


def test_absent_tags_stay_absent():
    assert EmbeddedTags.from_tag_values() == EmbeddedTags(title=None, artist=None, album=None, year=None, genres=())


@pytest.mark.parametrize("genres", ["Rock", ["Rock", 3]])
def test_embedded_tags_reject_genres_that_are_not_a_sequence_of_strings(genres):
    with pytest.raises(ValueError):
        EmbeddedTags(genres=genres)


def test_audio_probe_validates_duration():
    assert AudioProbe(audio_format="flac", duration_seconds=2).duration_seconds == 2.0
    with pytest.raises(ValueError):
        AudioProbe(audio_format=AudioFormat.FLAC, duration_seconds=-1)


# --- Entities ------------------------------------------------------------------------


def test_new_library_source_is_active_with_a_generated_id():
    source = new_library_source("C:/Music", _NOW)

    assert source.status is SourceStatus.ACTIVE
    assert source.created_at == _NOW
    assert source.last_scanned_at is None
    assert source.source_id != new_library_source("C:/Music", _NOW).source_id


@pytest.mark.parametrize("field, value", [("source_id", "1"), ("path", "  "), ("status", "GONE"), ("created_at", datetime(2026, 1, 1))])
def test_library_source_rejects_invalid_values(field, value):
    values = dict(source_id=_ID, path="/music", status=SourceStatus.ACTIVE, created_at=_NOW)
    values[field] = value
    with pytest.raises(ValueError):
        LibrarySource(**values)


def test_imported_source_file_needs_a_track_and_hash_and_no_reason():
    with pytest.raises(ValueError):
        _source_file(track_id=None)
    with pytest.raises(ValueError):
        _source_file(sha256=None)
    with pytest.raises(ValueError):
        _source_file(failure_reason=FailureReason.IO_ERROR)


@pytest.mark.parametrize("status", [SourceFileStatus.UNSUPPORTED, SourceFileStatus.FAILED])
def test_rejected_source_file_needs_a_reason(status):
    with pytest.raises(ValueError):
        _source_file(status=status, track_id=None, sha256=None)

    rejected = _source_file(status=status, track_id=None, sha256=None, failure_reason=FailureReason.IO_ERROR)
    assert rejected.failure_reason is FailureReason.IO_ERROR


def test_missing_source_file_may_keep_its_track_link():
    assert _source_file(status=SourceFileStatus.MISSING).track_id == _OTHER_ID


def test_source_file_matches_a_discovery_with_the_same_size_and_mtime():
    recorded = _source_file()

    assert recorded.matches(DiscoveredFile("album/song.mp3", 1000, 5))
    assert not recorded.matches(DiscoveredFile("album/song.mp3", 1001, 5))
    assert not recorded.matches(DiscoveredFile("album/song.mp3", 1000, 6))


@pytest.mark.parametrize(
    "field, value",
    [("sha256", "A" * 64), ("sha256", "a" * 63), ("size_bytes", -1), ("year", 0), ("year", 10000), ("duration_seconds", -0.1), ("original_filename", " ")],
)
def test_track_rejects_invalid_values(field, value):
    with pytest.raises(ValueError):
        _track(**{field: value})


def test_track_allows_at_most_one_primary_label_per_kind():
    genre = TrackLabel(kind=LabelKind.GENRE, value="Rock", source=EMBEDDED_TAGS_SOURCE, is_primary=True)
    mood = TrackLabel(kind=LabelKind.MOOD, value="calm", source="analyzer", is_primary=True, confidence=0.7)

    assert len(_track(labels=(genre, mood)).labels) == 2
    with pytest.raises(ValueError):
        _track(labels=(genre, replace(genre, value="Pop")))


@pytest.mark.parametrize("confidence", [-0.1, 1.1, True])
def test_label_confidence_must_be_a_fraction(confidence):
    with pytest.raises(ValueError):
        TrackLabel(kind=LabelKind.MOOD, value="calm", source="analyzer", is_primary=False, confidence=confidence)


def test_with_embedded_tags_sets_metadata_and_declared_genres():
    later = _NOW + timedelta(seconds=5)
    tags = EmbeddedTags(title="Song", artist="Artist", album="Album", year=2001, genres=("Jazz", "Blues"))

    track = _track().with_embedded_tags(tags, later)

    assert (track.title, track.artist, track.album, track.year) == ("Song", "Artist", "Album", 2001)
    assert track.genres == ("Jazz", "Blues")
    assert [label.is_primary for label in track.labels] == [True, False]
    assert all(label.source == EMBEDDED_TAGS_SOURCE and label.confidence is None for label in track.labels)
    assert track.updated_at == later


def test_with_embedded_tags_replaces_earlier_embedded_tags_and_keeps_other_sources():
    analyzed = TrackLabel(kind=LabelKind.GENRE, value="Ambient", source="analyzer", is_primary=True, confidence=0.9)
    track = _track(labels=(analyzed,)).with_embedded_tags(EmbeddedTags(title="Old", genres=("Rock",)), _NOW)

    retagged = track.with_embedded_tags(EmbeddedTags(genres=("Pop",)), _NOW)

    assert retagged.title is None
    assert retagged.genres == ("Ambient", "Pop")
    declared = [label for label in retagged.labels if label.source == EMBEDDED_TAGS_SOURCE]
    assert [(label.value, label.is_primary) for label in declared] == [("Pop", False)]


def test_with_status_changes_status_and_updated_at():
    later = _NOW + timedelta(minutes=1)

    track = _track().with_status(TrackStatus.MISSING_MANAGED_FILE, later)

    assert track.status is TrackStatus.MISSING_MANAGED_FILE
    assert track.updated_at == later


@pytest.mark.parametrize("value", [0, -1, 1.5, True])
def test_library_policy_requires_a_positive_size_limit(value):
    with pytest.raises(ValueError):
        LibraryPolicy(max_file_bytes=value)
