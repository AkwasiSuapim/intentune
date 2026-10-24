"""Deterministic synthetic libraries for B11: database tracks for scale, and real tagged audio files for import.

Synthetic data is measurement scaffolding only. It lives in scratch databases and folders; nothing here touches a
real library, and no feature value is ever written to a real track (D21).
"""

import hashlib
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import soundfile
from mutagen.flac import FLAC

from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.ports.unit_of_work import UnitOfWork

GENRES = ("Afrobeats", "Ambient", "Classical", "Electronic", "Hip-Hop", "Jazz", "Lofi", "Metal", "Pop", "Reggae", "Rock", "Soul")
MOODS = ("Calm", "Driven", "Emotional", "Focused", "Joyful")
_NOW = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)


def track_id(seed: int, number: int) -> str:
    """A stable canonical UUID for the number-th synthetic track of a seed."""
    return str(uuid.UUID(int=random.Random(f"{seed}:{number}").getrandbits(128), version=4))


def seed_tracks(
    unit_of_work: UnitOfWork, count: int, seed: int = 0, mood_share: float = 0.3, analysis_version: Optional[str] = None
) -> List[str]:
    """Add count playable tracks with a genre each (as the importer gives them) and a mood for some. Returns their ids.

    Roughly four tracks per artist, as in a personal library. One transaction. They have no managed copy, so a
    running analysis worker would rightly mark them MISSING_MANAGED_FILE; analysis_version set to the analyzer's
    key marks them as already analyzed, so it leaves them alone.
    """
    rng = random.Random(seed)
    ids = []
    artists = max(1, count // 4)
    with unit_of_work:
        for number in range(count):
            labels = [TrackLabel(LabelKind.GENRE, rng.choice(GENRES), "synthetic", True)]
            if rng.random() < mood_share:
                labels.append(TrackLabel(LabelKind.MOOD, rng.choice(MOODS), "synthetic", True))
            identifier = track_id(seed, number)
            unit_of_work.tracks.add(Track(
                track_id=identifier, sha256=hashlib.sha256(f"{seed}:{number}".encode()).hexdigest(), size_bytes=8_000_000,
                audio_format=AudioFormat.FLAC, status=TrackStatus.READY, original_filename=f"track-{number:05d}.flac",
                created_at=_NOW, updated_at=_NOW, title=f"Track {number}", artist=f"Artist {rng.randrange(artists)}",
                analysis_version=analysis_version, labels=tuple(labels),
            ))
            ids.append(identifier)
        unit_of_work.commit()
    return ids


def add_labelled_tracks(unit_of_work: UnitOfWork, labels: Sequence[Tuple[str, Optional[str]]], seed: int = 0) -> List[str]:
    """Add one playable track per (genre, mood) pair (mood may be None), titled after its genre. Returns their ids."""
    ids = []
    with unit_of_work:
        for number, (genre, mood) in enumerate(labels):
            track_labels = [TrackLabel(LabelKind.GENRE, genre, "synthetic", True)]
            if mood is not None:
                track_labels.append(TrackLabel(LabelKind.MOOD, mood, "synthetic", True))
            identifier = track_id(seed, number)
            unit_of_work.tracks.add(Track(
                track_id=identifier, sha256=hashlib.sha256(f"labelled:{seed}:{number}".encode()).hexdigest(), size_bytes=8_000_000,
                audio_format=AudioFormat.FLAC, status=TrackStatus.READY, original_filename=f"track-{number:05d}.flac",
                created_at=_NOW, updated_at=_NOW, title=f"{genre} {number}", artist=f"{genre} Artist {number % 3}",
                labels=tuple(track_labels),
            ))
            ids.append(identifier)
        unit_of_work.commit()
    return ids


def write_audio_library(folder: Path, count: int, seconds: float = 5.0, seed: int = 0) -> List[Path]:
    """Write count real FLAC tones with title, artist, and genre tags. Each differs in content, so in SHA-256."""
    rng = random.Random(seed)
    folder.mkdir(parents=True, exist_ok=True)
    rate = 44100
    times = np.arange(int(rate * seconds)) / rate
    paths = []
    for number in range(count):
        path = folder / f"tone-{number:05d}.flac"
        frequency = 220.0 + number % 800 + rng.random()
        signal = (0.2 + 0.6 * rng.random()) * np.sin(2 * np.pi * frequency * times)
        soundfile.write(str(path), np.repeat(signal[:, None], 2, axis=1), rate, format="FLAC", subtype="PCM_16")
        tags = FLAC(str(path))
        tags["title"], tags["artist"], tags["genre"] = f"Tone {number}", f"Artist {number % max(1, count // 4)}", rng.choice(GENRES)
        tags.save()
        paths.append(path)
    return paths
