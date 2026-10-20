"""SQLite library repositories against a migrated database: round trips, label handling, and database constraints."""

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.intentune.domain.library import (
    EMBEDDED_TAGS_SOURCE,
    AudioFormat,
    FailureReason,
    LabelKind,
    SourceFile,
    SourceFileStatus,
    SourceStatus,
    Track,
    TrackLabel,
    TrackStatus,
    new_library_source,
)

_NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def _track(sha_char="a", **overrides):
    values = dict(
        track_id=str(uuid.uuid4()),
        sha256=sha_char * 64,
        size_bytes=1000,
        audio_format=AudioFormat.FLAC,
        status=TrackStatus.IMPORTED,
        original_filename="song.flac",
        created_at=_NOW,
        updated_at=_NOW,
    )
    values.update(overrides)
    return Track(**values)


def _source_file(source_id, track_id=None, relative_path="a/song.flac", **overrides):
    values = dict(
        source_file_id=str(uuid.uuid4()),
        source_id=source_id,
        relative_path=relative_path,
        size_bytes=1000,
        modified_ns=7,
        status=SourceFileStatus.IMPORTED if track_id else SourceFileStatus.UNSUPPORTED,
        created_at=_NOW,
        updated_at=_NOW,
        sha256="a" * 64 if track_id else None,
        track_id=track_id,
        failure_reason=None if track_id else FailureReason.UNSUPPORTED_FORMAT,
    )
    values.update(overrides)
    return SourceFile(**values)


def _commit(unit_of_work, stage):
    with unit_of_work:
        stage(unit_of_work)
        unit_of_work.commit()


# --- Sources ---------------------------------------------------------------------


def test_library_source_round_trip(unit_of_work):
    first = new_library_source("/music/a", _NOW)
    second = new_library_source("/music/b", _NOW + timedelta(seconds=1))
    _commit(unit_of_work, lambda uow: (uow.library_sources.add(second), uow.library_sources.add(first)))

    with unit_of_work:
        assert unit_of_work.library_sources.get(first.source_id) == first
        assert unit_of_work.library_sources.get_by_path("/music/b") == second
        assert unit_of_work.library_sources.get_by_path("/music/c") is None
        assert unit_of_work.library_sources.list_all() == [first, second]


def test_library_source_save(unit_of_work):
    source = new_library_source("/music/a", _NOW)
    _commit(unit_of_work, lambda uow: uow.library_sources.add(source))
    scanned = replace(source, status=SourceStatus.MISSING, last_scanned_at=_NOW + timedelta(hours=1))

    _commit(unit_of_work, lambda uow: uow.library_sources.save(scanned))

    with unit_of_work:
        assert unit_of_work.library_sources.get(source.source_id) == scanned


def test_a_folder_can_be_registered_only_once(unit_of_work):
    _commit(unit_of_work, lambda uow: uow.library_sources.add(new_library_source("/music/a", _NOW)))

    with pytest.raises(IntegrityError):
        _commit(unit_of_work, lambda uow: uow.library_sources.add(new_library_source("/music/a", _NOW)))


def test_saving_an_unknown_source_raises(unit_of_work):
    with unit_of_work:
        with pytest.raises(LookupError):
            unit_of_work.library_sources.save(new_library_source("/music/a", _NOW))


# --- Tracks ----------------------------------------------------------------------


def test_track_round_trip_with_labels(unit_of_work):
    labels = (
        TrackLabel(kind=LabelKind.GENRE, value="Jazz", source=EMBEDDED_TAGS_SOURCE, is_primary=True),
        TrackLabel(kind=LabelKind.GENRE, value="Blues", source=EMBEDDED_TAGS_SOURCE, is_primary=False),
        TrackLabel(kind=LabelKind.MOOD, value="calm", source="analyzer", is_primary=True, confidence=0.75),
    )
    track = _track(title="Song", artist="Artist", album="Album", year=1999, duration_seconds=2.5, labels=labels)
    _commit(unit_of_work, lambda uow: uow.tracks.add(track))

    with unit_of_work:
        loaded = unit_of_work.tracks.get(track.track_id)
        by_hash = unit_of_work.tracks.get_by_sha256(track.sha256)

    assert loaded == by_hash
    assert replace(loaded, labels=()) == replace(track, labels=())
    assert set(loaded.labels) == set(labels)
    assert loaded.genres == ("Jazz", "Blues")


def test_unknown_tracks_are_none(unit_of_work):
    with unit_of_work:
        assert unit_of_work.tracks.get(str(uuid.uuid4())) is None
        assert unit_of_work.tracks.get_by_sha256("f" * 64) is None
        assert unit_of_work.tracks.list_all() == []


def test_list_all_returns_tracks_in_import_order_with_their_own_labels(unit_of_work):
    later = _track("b", created_at=_NOW + timedelta(seconds=1), labels=(TrackLabel(kind="genre", value="Rock", source="x", is_primary=True),))
    earlier = _track("a", labels=(TrackLabel(kind="genre", value="Pop", source="x", is_primary=True),))
    _commit(unit_of_work, lambda uow: (uow.tracks.add(later), uow.tracks.add(earlier)))

    with unit_of_work:
        tracks = unit_of_work.tracks.list_all()

    assert [track.track_id for track in tracks] == [earlier.track_id, later.track_id]
    assert [track.genres for track in tracks] == [("Pop",), ("Rock",)]


def test_save_replaces_track_fields_and_labels(unit_of_work):
    track = _track(labels=(TrackLabel(kind="genre", value="Rock", source=EMBEDDED_TAGS_SOURCE, is_primary=True),))
    _commit(unit_of_work, lambda uow: uow.tracks.add(track))
    changed = replace(
        track,
        status=TrackStatus.MISSING_MANAGED_FILE,
        title="New",
        updated_at=_NOW + timedelta(minutes=1),
        labels=(TrackLabel(kind="genre", value="Pop", source=EMBEDDED_TAGS_SOURCE, is_primary=True),),
    )

    _commit(unit_of_work, lambda uow: uow.tracks.save(changed))

    with unit_of_work:
        assert unit_of_work.tracks.get(track.track_id) == changed


def test_ids_with_status(unit_of_work):
    available = _track("a")
    missing = _track("b", status=TrackStatus.MISSING_MANAGED_FILE)
    _commit(unit_of_work, lambda uow: (uow.tracks.add(available), uow.tracks.add(missing)))

    with unit_of_work:
        assert unit_of_work.tracks.ids_with_status(TrackStatus.MISSING_MANAGED_FILE) == {missing.track_id}
        assert unit_of_work.tracks.ids_with_status(TrackStatus.IMPORTED) == {available.track_id}


def test_the_same_content_cannot_be_two_tracks(unit_of_work):
    _commit(unit_of_work, lambda uow: uow.tracks.add(_track("a")))

    with pytest.raises(IntegrityError):
        _commit(unit_of_work, lambda uow: uow.tracks.add(_track("a")))


def test_saving_an_unknown_track_raises(unit_of_work):
    with unit_of_work:
        with pytest.raises(LookupError):
            unit_of_work.tracks.save(_track())


# --- Source files ----------------------------------------------------------------


def test_source_file_round_trip_and_save(unit_of_work):
    source = new_library_source("/music/a", _NOW)
    track = _track()
    imported = _source_file(source.source_id, track.track_id, relative_path="b/imported.flac")
    rejected = _source_file(source.source_id, relative_path="a/rejected.mp3")
    _commit(unit_of_work, lambda uow: (uow.library_sources.add(source), uow.tracks.add(track), uow.source_files.add(imported), uow.source_files.add(rejected)))

    with unit_of_work:
        assert unit_of_work.source_files.list_for_source(source.source_id) == [rejected, imported]

    missing = replace(imported, status=SourceFileStatus.MISSING, updated_at=_NOW + timedelta(days=1))
    _commit(unit_of_work, lambda uow: uow.source_files.save(missing))

    with unit_of_work:
        assert unit_of_work.source_files.list_for_source(source.source_id) == [rejected, missing]


def test_a_relative_path_is_recorded_once_per_source(unit_of_work):
    first = new_library_source("/music/a", _NOW)
    second = new_library_source("/music/b", _NOW)
    _commit(
        unit_of_work,
        lambda uow: (
            uow.library_sources.add(first),
            uow.library_sources.add(second),
            uow.source_files.add(_source_file(first.source_id)),
            uow.source_files.add(_source_file(second.source_id)),
        ),
    )

    with pytest.raises(IntegrityError):
        _commit(unit_of_work, lambda uow: uow.source_files.add(_source_file(first.source_id)))


def test_source_files_must_belong_to_a_registered_source(unit_of_work):
    with pytest.raises(IntegrityError):
        _commit(unit_of_work, lambda uow: uow.source_files.add(_source_file(str(uuid.uuid4()))))


def test_source_files_can_only_reference_existing_tracks(unit_of_work):
    source = new_library_source("/music/a", _NOW)
    _commit(unit_of_work, lambda uow: uow.library_sources.add(source))

    with pytest.raises(IntegrityError):
        _commit(unit_of_work, lambda uow: uow.source_files.add(_source_file(source.source_id, str(uuid.uuid4()))))


# --- Database-level rules ----------------------------------------------------------

_TRACK_COLUMNS = "id, sha256, size_bytes, audio_format, status, original_filename, created_at, updated_at"


def _insert_track(connection, track_id, sha_char, audio_format="flac", status="IMPORTED"):
    connection.exec_driver_sql(
        f"INSERT INTO tracks ({_TRACK_COLUMNS}) VALUES (?, ?, 1, ?, ?, 'x.flac', '2026-10-19 12:00:00', '2026-10-19 12:00:00')",
        (track_id, sha_char * 64, audio_format, status),
    )


@pytest.mark.parametrize("audio_format", [audio_format.value for audio_format in AudioFormat])
def test_database_accepts_every_domain_audio_format(engine, audio_format):
    with engine.begin() as connection:
        _insert_track(connection, str(uuid.uuid4()), "a", audio_format=audio_format)


@pytest.mark.parametrize("status", [status.value for status in TrackStatus])
def test_database_accepts_every_domain_track_status(engine, status):
    with engine.begin() as connection:
        _insert_track(connection, str(uuid.uuid4()), "a", status=status)


@pytest.mark.parametrize("column, value", [("audio_format", "exe"), ("status", "READY"), ("status", "imported")])
def test_database_rejects_values_the_domain_does_not_define(engine, column, value):
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            _insert_track(connection, str(uuid.uuid4()), "a", **{column: value})


def test_database_rejects_an_imported_source_file_without_a_track(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO library_sources (id, path, status, created_at) VALUES ('3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e', '/m', 'ACTIVE', '2026-10-19 12:00:00')"
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO source_files (id, source_id, relative_path, size_bytes, modified_ns, status, created_at, updated_at) "
                "VALUES ('9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d', '3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e', 'a.mp3', 1, 1, 'IMPORTED', '2026-10-19 12:00:00', '2026-10-19 12:00:00')"
            )


def test_database_allows_one_primary_label_per_kind_per_track(engine):
    track_id = str(uuid.uuid4())
    insert_label = (
        "INSERT INTO track_labels (id, track_id, kind, value, source, is_primary) VALUES (?, ?, ?, ?, 'tags', ?)"
    )
    with engine.begin() as connection:
        _insert_track(connection, track_id, "a")
        connection.exec_driver_sql(insert_label, (str(uuid.uuid4()), track_id, "genre", "Rock", 1))
        connection.exec_driver_sql(insert_label, (str(uuid.uuid4()), track_id, "genre", "Pop", 0))
        connection.exec_driver_sql(insert_label, (str(uuid.uuid4()), track_id, "mood", "calm", 1))

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(insert_label, (str(uuid.uuid4()), track_id, "genre", "Jazz", 1))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(insert_label, (str(uuid.uuid4()), track_id, "genre", "Ska", 2))
