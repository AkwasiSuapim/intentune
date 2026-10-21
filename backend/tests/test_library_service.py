"""LibraryService end to end: real files, real adapters, a migrated SQLite database, and a temporary media folder.

The five behaviors the execution guide requires for B2 are each proven here:
multiple sources coexist, an exact duplicate is not duplicated, the managed
copy survives deletion of the original, unsupported formats fail safely, and
rescanning is incremental (verified by counting the work done, not only by
the report).
"""

import hashlib
import os
import shutil
import uuid

import pytest

from src.intentune.adapters.local_folders import LocalSourceFolders
from src.intentune.adapters.managed_media import LocalManagedMedia
from src.intentune.adapters.mutagen_audio import MutagenAudioInspector
from src.intentune.application.library import ImportOutcome, LibraryPolicy, LibraryService
from src.intentune.domain.library import (
    AudioFormat,
    DiscoveredFile,
    FailureReason,
    InvalidLibrarySource,
    LibrarySourceNotFound,
    ScanReport,
    SourceFileStatus,
    SourceStatus,
    TagReadError,
    TrackNotFound,
    TrackStatus,
    TrackUnavailable,
    UnsupportedAudioFile,
)


class CountingFolders(LocalSourceFolders):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hashed = []
        self.fail_next_hash = None

    def sha256(self, path):
        self.hashed.append(path)
        failure, self.fail_next_hash = self.fail_next_hash, None
        if failure == "os_error":
            raise OSError("simulated read failure")
        if failure == "wrong_digest":
            return "0" * 64
        return super().sha256(path)


class CountingInspector(MutagenAudioInspector):
    def __init__(self):
        self.probed = []
        self.fail_tags = False

    def probe(self, path, audio_format):
        self.probed.append(path)
        return super().probe(path, audio_format)

    def read_tags(self, path):
        if self.fail_tags:
            raise TagReadError("simulated tag failure")
        return super().read_tags(path)


class CountingMedia(LocalManagedMedia):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stored = []

    def store(self, source_path, track_id, audio_format, expected_sha256):
        self.stored.append(track_id)
        return super().store(source_path, track_id, audio_format, expected_sha256)


class Spies:
    def __init__(self, media_root):
        self.folders = CountingFolders(excluded_directories=[media_root])
        self.inspector = CountingInspector()
        self.media = CountingMedia(media_root)

    def reset(self):
        self.folders.hashed.clear()
        self.inspector.probed.clear()
        self.media.stored.clear()


@pytest.fixture
def spies(media_root):
    return Spies(media_root)


@pytest.fixture
def spied_library(unit_of_work, spies):
    return LibraryService(unit_of_work, spies.folders, spies.inspector, spies.media)


@pytest.fixture
def music(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    return root


def _source_files(unit_of_work, source_id):
    with unit_of_work:
        return {source_file.relative_path: source_file for source_file in unit_of_work.source_files.list_for_source(source_id)}


def _managed_names(media_root):
    return sorted(path.name for path in media_root.iterdir()) if media_root.exists() else []


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- Sources ---------------------------------------------------------------------


def test_register_source_records_the_normalized_folder_once(library, music):
    (music / "sub").mkdir()

    source = library.register_source(str(music))

    assert source.path == str(music.resolve())
    assert source.status is SourceStatus.ACTIVE
    assert source.last_scanned_at is None
    assert library.register_source(str(music / "sub" / "..")) == source
    assert library.list_sources() == [source]


def test_register_source_rejects_paths_that_are_not_usable_folders(library, music, media_root):
    (music / "song.mp3").write_bytes(b"x")
    media_root.mkdir()

    for path in (music / "song.mp3", music / "missing", media_root):
        with pytest.raises(InvalidLibrarySource):
            library.register_source(str(path))
    assert library.list_sources() == []


# --- Import ----------------------------------------------------------------------


def test_scan_imports_tracks_with_basic_metadata_into_managed_media(library, audio, music, media_root, unit_of_work):
    flac = audio.flac(music / "Artist" / "Album" / "01 Song.flac", TITLE="Song", artist="Artist", album="Album", date="1999", genre=["Jazz", "Blues"])
    mp3 = audio.mp3(music / "b.mp3", title="Bee")
    source = library.register_source(str(music))

    report = library.scan_source(source.source_id)

    assert report == ScanReport(source_id=source.source_id, imported=2)
    tracks = {track.original_filename: track for track in library.list_tracks()}
    song = tracks["01 Song.flac"]
    assert (song.title, song.artist, song.album, song.year, song.genres) == ("Song", "Artist", "Album", 1999, ("Jazz", "Blues"))
    assert song.duration_seconds == pytest.approx(2.0)
    assert song.status is TrackStatus.IMPORTED
    assert song.analysis_version is None
    assert song.audio_format is AudioFormat.FLAC
    assert song.sha256 == _sha256(flac)
    assert song.size_bytes == flac.stat().st_size
    assert tracks["b.mp3"].title == "Bee"

    assert _managed_names(media_root) == sorted(f"{track.track_id}.{track.audio_format.extension}" for track in tracks.values())
    assert (media_root / f"{song.track_id}.flac").read_bytes() == flac.read_bytes()
    assert (media_root / f"{tracks['b.mp3'].track_id}.mp3").read_bytes() == mp3.read_bytes()

    rows = _source_files(unit_of_work, source.source_id)
    assert rows["Artist/Album/01 Song.flac"].status is SourceFileStatus.IMPORTED
    assert rows["Artist/Album/01 Song.flac"].track_id == song.track_id
    scanned = library.list_sources()[0]
    assert scanned.status is SourceStatus.ACTIVE
    assert scanned.last_scanned_at is not None


def test_multiple_sources_coexist(library, audio, tmp_path):
    first_folder = tmp_path / "first"
    second_folder = tmp_path / "second"
    audio.mp3(first_folder / "one.mp3", seed=1)
    audio.flac(second_folder / "two.flac", seed=2)

    first = library.register_source(str(first_folder))
    library.scan_source(first.source_id)
    second = library.register_source(str(second_folder))
    library.scan_source(second.source_id)

    assert [source.source_id for source in library.list_sources()] == [first.source_id, second.source_id]
    assert sorted(track.original_filename for track in library.list_tracks()) == ["one.mp3", "two.flac"]
    reports = library.rescan_library()
    assert reports == [ScanReport(source_id=first.source_id, unchanged=1), ScanReport(source_id=second.source_id, unchanged=1)]


def test_exact_duplicate_is_not_duplicated(library, audio, tmp_path, media_root, unit_of_work):
    first_folder = tmp_path / "first"
    second_folder = tmp_path / "second"
    original = audio.mp3(first_folder / "song.mp3", title="Same", seed=5)
    shutil.copyfile(original, first_folder / "copy of song.mp3")
    (second_folder / "elsewhere").mkdir(parents=True)
    shutil.copyfile(original, second_folder / "elsewhere" / "renamed.mp3")
    first = library.register_source(str(first_folder))
    second = library.register_source(str(second_folder))

    first_report = library.scan_source(first.source_id)
    second_report = library.scan_source(second.source_id)

    assert first_report == ScanReport(source_id=first.source_id, imported=1, duplicates=1)
    assert second_report == ScanReport(source_id=second.source_id, duplicates=1)
    tracks = library.list_tracks()
    assert len(tracks) == 1
    assert _managed_names(media_root) == [f"{tracks[0].track_id}.mp3"]
    linked = list(_source_files(unit_of_work, first.source_id).values()) + list(_source_files(unit_of_work, second.source_id).values())
    assert len(linked) == 3
    assert {row.track_id for row in linked} == {tracks[0].track_id}
    assert all(row.status is SourceFileStatus.IMPORTED for row in linked)


def test_managed_copy_survives_deletion_of_the_original(library, audio, music, media_root, unit_of_work):
    original = audio.flac(music / "song.flac", TITLE="Keep me")
    original_bytes = original.read_bytes()
    source = library.register_source(str(music))
    library.scan_source(source.source_id)
    [track] = library.list_tracks()

    original.unlink()

    managed = media_root / f"{track.track_id}.flac"
    assert managed.read_bytes() == original_bytes
    assert library.get_track(track.track_id).status is TrackStatus.IMPORTED
    assert library.scan_source(source.source_id) == ScanReport(source_id=source.source_id, missing=1)
    assert library.get_track(track.track_id) == track
    assert managed.read_bytes() == original_bytes
    row = _source_files(unit_of_work, source.source_id)["song.flac"]
    assert row.status is SourceFileStatus.MISSING
    assert row.track_id == track.track_id
    assert library.scan_source(source.source_id) == ScanReport(source_id=source.source_id)


def test_a_missing_source_folder_is_marked_missing_and_keeps_its_tracks(library, audio, music, tmp_path, media_root):
    audio.mp3(music / "song.mp3")
    source = library.register_source(str(music))
    library.scan_source(source.source_id)
    [track] = library.list_tracks()
    unplugged = tmp_path / "unplugged"
    music.rename(unplugged)

    assert library.scan_source(source.source_id) == ScanReport(source_id=source.source_id, source_missing=True)
    assert library.list_sources()[0].status is SourceStatus.MISSING
    assert library.get_track(track.track_id).status is TrackStatus.IMPORTED
    assert (media_root / f"{track.track_id}.mp3").is_file()

    unplugged.rename(music)
    assert library.scan_source(source.source_id) == ScanReport(source_id=source.source_id, unchanged=1)
    assert library.list_sources()[0].status is SourceStatus.ACTIVE


def test_unsupported_files_fail_safely(unit_of_work, spies, audio, music, media_root):
    library = LibraryService(unit_of_work, spies.folders, spies.inspector, spies.media, policy=LibraryPolicy(max_file_bytes=20_000))
    good = audio.mp3(music / "good.mp3", seed=1)
    (music / "fake.mp3").write_text("not audio at all\n" * 50, encoding="utf-8")
    audio.mp3(music / "mislabeled.flac", seed=2)
    audio.mp3(music / "big.mp3", seed=3, frames=100)
    (music / "notes.txt").write_text("liner notes", encoding="utf-8")
    (music / "cover.jpg").write_bytes(b"\xff\xd8\xff")
    (music / "song.wma").write_bytes(b"wma")
    assert good.stat().st_size < 20_000 < (music / "big.mp3").stat().st_size
    source = library.register_source(str(music))

    report = library.scan_source(source.source_id)

    assert report == ScanReport(source_id=source.source_id, imported=1, unsupported=3, ignored=3)
    [track] = library.list_tracks()
    assert track.original_filename == "good.mp3"
    assert _managed_names(media_root) == [f"{track.track_id}.mp3"]
    rows = _source_files(unit_of_work, source.source_id)
    assert sorted(rows) == ["big.mp3", "fake.mp3", "good.mp3", "mislabeled.flac"]
    assert (rows["fake.mp3"].status, rows["fake.mp3"].failure_reason) == (SourceFileStatus.UNSUPPORTED, FailureReason.UNSUPPORTED_FORMAT)
    assert rows["mislabeled.flac"].failure_reason is FailureReason.UNSUPPORTED_FORMAT
    assert rows["big.mp3"].failure_reason is FailureReason.FILE_TOO_LARGE
    assert all(rows[name].track_id is None for name in ("big.mp3", "fake.mp3", "mislabeled.flac"))

    spies.reset()
    assert library.scan_source(source.source_id) == ScanReport(source_id=source.source_id, unchanged=4, ignored=3)
    assert spies.inspector.probed == []


# --- Incremental rescans -------------------------------------------------------------


def test_rescan_of_an_unchanged_source_does_no_work(spied_library, spies, audio, music, unit_of_work):
    audio.mp3(music / "a.mp3", seed=1)
    audio.wav(music / "b.wav", seed=2)
    audio.flac(music / "c" / "c.flac", seed=3)
    source = spied_library.register_source(str(music))
    spied_library.scan_source(source.source_id)
    tracks_before = spied_library.list_tracks()
    rows_before = _source_files(unit_of_work, source.source_id)
    spies.reset()

    report = spied_library.scan_source(source.source_id)

    assert report == ScanReport(source_id=source.source_id, unchanged=3)
    assert (spies.folders.hashed, spies.inspector.probed, spies.media.stored) == ([], [], [])
    assert spied_library.list_tracks() == tracks_before
    assert _source_files(unit_of_work, source.source_id) == rows_before


def test_a_touched_file_with_the_same_content_is_rehashed_but_not_reimported(spied_library, spies, audio, music, unit_of_work):
    song = audio.mp3(music / "song.mp3")
    source = spied_library.register_source(str(music))
    spied_library.scan_source(source.source_id)
    [track] = spied_library.list_tracks()
    details = song.stat()
    os.utime(song, ns=(details.st_atime_ns, details.st_mtime_ns + 5_000_000_000))
    spies.reset()

    report = spied_library.scan_source(source.source_id)

    assert report == ScanReport(source_id=source.source_id, unchanged=1)
    assert len(spies.folders.hashed) == 1
    assert spies.media.stored == []
    assert spied_library.list_tracks() == [track]
    assert _source_files(unit_of_work, source.source_id)["song.mp3"].modified_ns == song.stat().st_mtime_ns


def test_changed_content_becomes_a_new_track_and_the_old_one_stays(library, audio, music, media_root, unit_of_work):
    song = music / "song.mp3"
    audio.mp3(song, seed=1, title="First take")
    source = library.register_source(str(music))
    library.scan_source(source.source_id)
    [old] = library.list_tracks()
    old_mtime = song.stat().st_mtime_ns
    audio.mp3(song, seed=2, title="Second take")
    os.utime(song, ns=(old_mtime, old_mtime + 5_000_000_000))

    report = library.scan_source(source.source_id)

    assert report == ScanReport(source_id=source.source_id, imported=1)
    new = next(track for track in library.list_tracks() if track.track_id != old.track_id)
    assert new.title == "Second take"
    assert library.get_track(old.track_id) == old
    assert (media_root / f"{old.track_id}.mp3").is_file()
    assert _source_files(unit_of_work, source.source_id)["song.mp3"].track_id == new.track_id


def test_a_failed_file_is_retried_on_the_next_scan(spied_library, spies, audio, music, unit_of_work):
    audio.mp3(music / "song.mp3")
    source = spied_library.register_source(str(music))
    spies.folders.fail_next_hash = "os_error"

    assert spied_library.scan_source(source.source_id) == ScanReport(source_id=source.source_id, failed=1)
    row = _source_files(unit_of_work, source.source_id)["song.mp3"]
    assert (row.status, row.failure_reason, row.track_id) == (SourceFileStatus.FAILED, FailureReason.IO_ERROR, None)
    assert spied_library.list_tracks() == []

    assert spied_library.scan_source(source.source_id) == ScanReport(source_id=source.source_id, imported=1)
    assert _source_files(unit_of_work, source.source_id)["song.mp3"].status is SourceFileStatus.IMPORTED


def test_a_file_that_changes_during_import_leaves_no_managed_copy(spied_library, spies, audio, music, media_root, unit_of_work):
    audio.mp3(music / "song.mp3")
    source = spied_library.register_source(str(music))
    spies.folders.fail_next_hash = "wrong_digest"

    assert spied_library.scan_source(source.source_id) == ScanReport(source_id=source.source_id, failed=1)
    assert _source_files(unit_of_work, source.source_id)["song.mp3"].failure_reason is FailureReason.CHANGED_DURING_IMPORT
    assert _managed_names(media_root) == []
    assert spied_library.list_tracks() == []

    assert spied_library.scan_source(source.source_id) == ScanReport(source_id=source.source_id, imported=1)


def test_a_tag_read_failure_keeps_the_track_playable(spied_library, spies, audio, music, media_root):
    audio.mp3(music / "song.mp3", title="Unread")
    source = spied_library.register_source(str(music))
    spies.inspector.fail_tags = True

    assert spied_library.scan_source(source.source_id) == ScanReport(source_id=source.source_id, imported=1, tag_failures=1)
    [track] = spied_library.list_tracks()
    assert track.status is TrackStatus.IMPORTED
    assert track.title is None
    assert (media_root / f"{track.track_id}.mp3").is_file()


def test_managed_media_inside_a_source_is_never_scanned(library, audio, tmp_path, media_root):
    audio.mp3(tmp_path / "music" / "song.mp3")
    source = library.register_source(str(tmp_path))

    assert library.scan_source(source.source_id).imported == 1
    assert len(_managed_names(media_root)) == 1

    report = library.scan_source(source.source_id)
    assert (report.imported, report.duplicates, report.unchanged) == (0, 0, 1)
    assert len(library.list_tracks()) == 1


# --- Availability ------------------------------------------------------------------


def test_mark_unavailable_then_repair_on_rescan(library, audio, music, media_root):
    song = audio.flac(music / "song.flac", seed=9)
    source = library.register_source(str(music))
    library.scan_source(source.source_id)
    [track] = library.list_tracks()
    managed = media_root / f"{track.track_id}.flac"

    unavailable = library.mark_track_unavailable(track.track_id)
    assert unavailable.status is TrackStatus.MISSING_MANAGED_FILE
    assert library.mark_track_unavailable(track.track_id) == unavailable
    managed.unlink()

    assert library.scan_source(source.source_id) == ScanReport(source_id=source.source_id, repaired=1)
    assert managed.read_bytes() == song.read_bytes()
    assert library.get_track(track.track_id).status is TrackStatus.IMPORTED
    assert len(library.list_tracks()) == 1


def test_unknown_ids_raise(library):
    unknown = str(uuid.uuid4())

    with pytest.raises(TrackNotFound):
        library.get_track(unknown)
    with pytest.raises(TrackNotFound):
        library.mark_track_unavailable(unknown)
    with pytest.raises(LibrarySourceNotFound):
        library.scan_source(unknown)
    with pytest.raises(LibrarySourceNotFound):
        library.import_file(unknown, DiscoveredFile("song.mp3", 1, 1))


def test_import_file_runs_the_pipeline_for_one_discovered_file(library, audio, music):
    audio.mp3(music / "song.mp3", title="One")
    source = library.register_source(str(music))
    [discovered] = list(LocalSourceFolders().list_files(str(music)))

    first = library.import_file(source.source_id, discovered)
    again = library.import_file(source.source_id, discovered)

    assert first.outcome is ImportOutcome.IMPORTED
    assert library.get_track(first.track_id).title == "One"
    assert (again.outcome, again.track_id) == (ImportOutcome.UNCHANGED, first.track_id)
    with pytest.raises(UnsupportedAudioFile):
        library.import_file(source.source_id, DiscoveredFile("notes.txt", 1, 1))


# --- Tracks for the API (B8) -------------------------------------------------------


def test_get_tracks_reads_several_tracks_by_id_and_leaves_out_unknown_ids(library, audio, music):
    audio.mp3(music / "one.mp3", seed=1, title="One")
    audio.mp3(music / "two.mp3", seed=2, title="Two")
    library.scan_source(library.register_source(str(music)).source_id)
    one, two = sorted(library.list_tracks(), key=lambda track: track.title)

    found = library.get_tracks([two.track_id, one.track_id, two.track_id, str(uuid.uuid4())])

    assert found == {one.track_id: one, two.track_id: two}
    assert library.get_tracks([]) == {}


def test_track_audio_gives_the_managed_copy_of_a_playable_track(library, audio, music, media_root):
    audio.flac(music / "song.flac", TITLE="Song")
    library.scan_source(library.register_source(str(music)).source_id)
    [track] = library.list_tracks()

    found = library.track_audio(track.track_id)

    assert found.track == track
    assert found.path == str((media_root / f"{track.track_id}.flac").resolve())


def test_track_audio_of_a_missing_managed_copy_marks_the_track_unavailable(library, audio, music, media_root):
    audio.flac(music / "song.flac", TITLE="Song")
    library.scan_source(library.register_source(str(music)).source_id)
    [track] = library.list_tracks()
    (media_root / f"{track.track_id}.flac").unlink()

    with pytest.raises(TrackUnavailable):
        library.track_audio(track.track_id)

    assert library.get_track(track.track_id).status is TrackStatus.MISSING_MANAGED_FILE
    with pytest.raises(TrackUnavailable):
        library.track_audio(track.track_id)


def test_track_audio_refuses_a_track_already_unavailable_even_if_a_file_is_back(library, audio, music, media_root):
    audio.flac(music / "song.flac", TITLE="Song")
    library.scan_source(library.register_source(str(music)).source_id)
    [track] = library.list_tracks()
    library.mark_track_unavailable(track.track_id)

    with pytest.raises(TrackUnavailable):
        library.track_audio(track.track_id)  # the managed copy is still on disk; only a scan restores the track


def test_track_audio_of_an_unknown_track_raises_not_found(library):
    with pytest.raises(TrackNotFound):
        library.track_audio(str(uuid.uuid4()))
