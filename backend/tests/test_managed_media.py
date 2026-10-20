"""LocalManagedMedia: generated names, atomic hash-verified copies, and paths that cannot escape the media folder."""

import hashlib

import pytest

from src.intentune.adapters.managed_media import DEFAULT_MEDIA_ROOT, LocalManagedMedia
from src.intentune.domain.library import AudioFormat, ManagedCopyMismatch

_TRACK_ID = "3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e"


@pytest.fixture
def media(tmp_path):
    return LocalManagedMedia(tmp_path / "media")


@pytest.fixture
def source_file(tmp_path):
    path = tmp_path / "music" / "My Song (final).mp3"
    path.parent.mkdir()
    path.write_bytes(b"audio bytes" * 1000)
    return path


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_default_media_root_is_backend_data_media():
    assert DEFAULT_MEDIA_ROOT.parts[-3:] == ("backend", "data", "media")


def test_store_copies_under_a_generated_name(media, source_file):
    size = media.store(str(source_file), _TRACK_ID, AudioFormat.MP3, _sha256(source_file))

    managed = media.root / f"{_TRACK_ID}.mp3"
    assert media.path(_TRACK_ID, AudioFormat.MP3) == str(managed)
    assert managed.read_bytes() == source_file.read_bytes()
    assert size == source_file.stat().st_size
    assert [path.name for path in media.root.iterdir()] == [f"{_TRACK_ID}.mp3"]


def test_store_creates_the_media_folder(media, source_file):
    assert not media.root.exists()

    media.store(str(source_file), _TRACK_ID, AudioFormat.MP3, _sha256(source_file))

    assert media.root.is_dir()


def test_a_hash_mismatch_leaves_nothing_behind(media, source_file):
    with pytest.raises(ManagedCopyMismatch):
        media.store(str(source_file), _TRACK_ID, AudioFormat.MP3, "0" * 64)

    assert list(media.root.iterdir()) == []
    assert not media.exists(_TRACK_ID, AudioFormat.MP3)


def test_an_unreadable_source_raises_os_error_and_leaves_nothing_behind(media, tmp_path):
    with pytest.raises(OSError):
        media.store(str(tmp_path / "missing.mp3"), _TRACK_ID, AudioFormat.MP3, "0" * 64)

    assert not media.root.exists() or list(media.root.iterdir()) == []


def test_exists_and_discard(media, source_file):
    media.store(str(source_file), _TRACK_ID, AudioFormat.FLAC, _sha256(source_file))
    assert media.exists(_TRACK_ID, AudioFormat.FLAC)
    assert not media.exists(_TRACK_ID, AudioFormat.MP3)

    media.discard(_TRACK_ID, AudioFormat.FLAC)
    media.discard(_TRACK_ID, AudioFormat.FLAC)

    assert not media.exists(_TRACK_ID, AudioFormat.FLAC)


@pytest.mark.parametrize(
    "track_id",
    ["../escape", "..\\escape", "3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e/../../x", "3F2C4A8E-1B7D-4C55-9E0A-6D1F2B3C4D5E", "song"],
)
def test_paths_are_built_only_from_canonical_uuids(media, track_id):
    with pytest.raises(ValueError):
        media.path(track_id, AudioFormat.MP3)


@pytest.mark.parametrize("audio_format", ["exe", "mp3/../../x", ""])
def test_paths_are_built_only_from_allowlisted_formats(media, audio_format):
    with pytest.raises(ValueError):
        media.path(_TRACK_ID, audio_format)
