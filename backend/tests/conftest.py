"""Shared fixtures for persistence and library tests.

Every database here is a fresh SQLite file under pytest's tmp_path. No test
opens backend/data/intentune.db or depends on the DATABASE_URL variable.
Library tests also keep their source folders and managed media under
tmp_path, never backend/data/media/.
"""

import struct
import wave
from pathlib import Path

import numpy as np
import pytest
import soundfile
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TCON, TDRC, TIT2, TPE1
from mutagen.wave import WAVE

from src.intentune.adapters.local_folders import LocalSourceFolders
from src.intentune.adapters.managed_media import LocalManagedMedia
from src.intentune.adapters.mutagen_audio import MutagenAudioInspector
from src.intentune.application.library import LibraryService
from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.migrations import upgrade_database
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def database_url(tmp_path):
    """A URL for a database file that does not exist yet."""
    return f"sqlite:///{(tmp_path / 'intentune-test.db').as_posix()}"


@pytest.fixture
def migrated_database_url(database_url):
    """A database upgraded to the latest migration."""
    upgrade_database(database_url)
    return database_url


@pytest.fixture
def engine(migrated_database_url):
    engine = create_database_engine(migrated_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    return create_session_factory(engine)


@pytest.fixture
def unit_of_work(session_factory):
    return SqlAlchemyUnitOfWork(session_factory)


# --- Audio files -----------------------------------------------------------------


def _as_list(value):
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _id3_frames(title=None, artist=None, album=None, date=None, genre=None):
    frames = []
    if title is not None:
        frames.append(TIT2(encoding=3, text=_as_list(title)))
    if artist is not None:
        frames.append(TPE1(encoding=3, text=_as_list(artist)))
    if album is not None:
        frames.append(TALB(encoding=3, text=_as_list(album)))
    if date is not None:
        frames.append(TDRC(encoding=3, text=_as_list(date)))
    if genre is not None:
        frames.append(TCON(encoding=3, text=_as_list(genre)))
    return frames


_ENCODINGS = {
    ".wav": ("WAV", "PCM_16"),
    ".flac": ("FLAC", "PCM_16"),
    ".ogg": ("OGG", "VORBIS"),
    ".opus": ("OGG", "OPUS"),
    ".mp3": ("MP3", "MPEG_LAYER_III"),
}


class AudioSamples:
    """Writes small, valid audio files with optional embedded tags.

    mp3(), wav(), and flac() build minimal files by hand for the library tests.
    Tag keywords: title, artist, album, date, genre (a string or a list).
    Different seeds give different content, so different SHA-256 hashes.

    tone() encodes a real sine tone with libsndfile (WAV, FLAC, Ogg Vorbis,
    Opus, MP3), for analysis tests that decode actual audio.
    """

    @staticmethod
    def tone(path, amplitude=0.5, seconds=1.0, frequency=1000.0, channels=2, sample_rate=None, spike=None):
        """A sine tone of the given peak amplitude. spike=(frame, value) overwrites one frame on every channel."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        audio_format, subtype = _ENCODINGS[path.suffix.lower()]
        rate = sample_rate or (48000 if path.suffix.lower() == ".opus" else 44100)
        times = np.arange(int(rate * seconds)) / rate
        signal = amplitude * np.sin(2 * np.pi * frequency * times)
        if spike is not None:
            signal[spike[0]] = spike[1]
        soundfile.write(str(path), np.repeat(signal[:, None], channels, axis=1), rate, format=audio_format, subtype=subtype)
        return path

    @staticmethod
    def mp3(path, seed=1, frames=40, **tags):
        """MPEG-1 Layer III frames (128 kbps, 44.1 kHz) with an ID3 tag."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = bytes([0xFF, 0xFB, 0x90, 0x64]) + bytes([seed % 200]) * 413
        path.write_bytes(frame * frames)
        id3_frames = _id3_frames(**tags)
        if id3_frames:
            id3 = ID3()
            for id3_frame in id3_frames:
                id3.add(id3_frame)
            id3.save(path)
        return path

    @staticmethod
    def wav(path, seed=1, seconds=0.5, **tags):
        """16-bit mono PCM at 8 kHz, with an ID3 chunk if tags are given."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(8000)
            writer.writeframes(struct.pack("<h", seed) * int(8000 * seconds))
        id3_frames = _id3_frames(**tags)
        if id3_frames:
            audio = WAVE(str(path))
            audio.add_tags()
            for id3_frame in id3_frames:
                audio.tags.add(id3_frame)
            audio.save()
        return path

    @staticmethod
    def flac(path, seed=1, seconds=2, **tags):
        """A FLAC stream header (STREAMINFO only) with Vorbis comments."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        packed = (44100 << 44) | (1 << 41) | (15 << 36) | (44100 * seconds)
        streaminfo = struct.pack(">HH", 4096, 4096) + b"\x00" * 6 + struct.pack(">Q", packed) + bytes([seed % 256]) * 16
        path.write_bytes(b"fLaC" + bytes([0x80]) + len(streaminfo).to_bytes(3, "big") + streaminfo)
        if tags:
            audio = FLAC(str(path))
            for key, value in tags.items():
                audio[key] = _as_list(value)
            audio.save()
        return path


@pytest.fixture
def audio():
    return AudioSamples


# --- Library ---------------------------------------------------------------------


@pytest.fixture
def media_root(tmp_path):
    return tmp_path / "media"


@pytest.fixture
def library(unit_of_work, media_root):
    """A LibraryService over a migrated database, real adapters, and a temporary media folder."""
    return LibraryService(
        unit_of_work,
        LocalSourceFolders(excluded_directories=[media_root]),
        MutagenAudioInspector(),
        LocalManagedMedia(media_root),
    )
