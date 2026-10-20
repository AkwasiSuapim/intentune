"""AudioInspector adapter built on mutagen: validates audio files and reads their basic tags.

Validation is by content. mutagen identifies the file from its bytes, and
the result must be a type accepted for the format the extension claims: MP3
bytes named .ogg are rejected. A file mutagen cannot parse is unsupported,
except when the file itself could not be opened, which is reported as
OSError so the scan can retry it.

Tags are mapped from the three tag systems the allowlisted formats use:
ID3 (MP3, WAV), Vorbis comments (FLAC, Ogg Vorbis, Opus), and MP4 atoms (M4A).
Only title, artist, album, date (for the year), and genre are read (spec §6).
Artwork is not extracted in B2; how it would be served is an open question.
"""

from typing import List

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Tags
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from src.intentune.domain.library import AudioFormat, AudioProbe, EmbeddedTags, TagReadError, UnsupportedAudioFile

_ACCEPTED_TYPES = {
    AudioFormat.MP3: (MP3,),
    AudioFormat.M4A: (MP4,),
    AudioFormat.FLAC: (FLAC,),
    AudioFormat.OGG: (OggVorbis, OggOpus),
    AudioFormat.OPUS: (OggOpus,),
    AudioFormat.WAV: (WAVE,),
}

_ID3_FRAMES = {"titles": "TIT2", "artists": "TPE1", "albums": "TALB", "dates": "TDRC"}
_MP4_ATOMS = {"titles": "\xa9nam", "artists": "\xa9ART", "albums": "\xa9alb", "dates": "\xa9day", "genres": "\xa9gen"}
_VORBIS_KEYS = {"titles": "title", "artists": "artist", "albums": "album", "dates": "date", "genres": "genre"}


def _load(path: str):
    """mutagen's file object for path, or None if mutagen does not recognize the content."""
    try:
        return mutagen.File(path)
    except mutagen.MutagenError as error:
        if isinstance(error.__cause__, OSError):
            raise OSError(f"The file could not be read: {error.__cause__.strerror or error}") from error
        raise UnsupportedAudioFile("The file is not valid audio.") from error
    except OSError:
        raise
    except Exception as error:  # malformed input can surface as other errors inside the parsers
        raise UnsupportedAudioFile("The file is not valid audio.") from error


def _strings(values) -> List[str]:
    return [str(value) for value in values] if values else []


def embedded_tags_from(tags) -> EmbeddedTags:
    """Map a mutagen tag container (ID3, MP4Tags, or Vorbis comments) to EmbeddedTags."""
    if isinstance(tags, ID3):
        values = {name: _strings(getattr(tags.get(frame_id), "text", None)) for name, frame_id in _ID3_FRAMES.items()}
        genre_frame = tags.get("TCON")
        values["genres"] = list(genre_frame.genres) if genre_frame is not None else []
    elif isinstance(tags, MP4Tags):
        values = {name: _strings(tags.get(atom)) for name, atom in _MP4_ATOMS.items()}
    else:
        values = {name: _strings(tags.get(key)) for name, key in _VORBIS_KEYS.items()}
    return EmbeddedTags.from_tag_values(**values)


class MutagenAudioInspector:
    def probe(self, path: str, audio_format: AudioFormat) -> AudioProbe:
        audio_format = AudioFormat(audio_format)
        audio = _load(path)
        if audio is None or not isinstance(audio, _ACCEPTED_TYPES[audio_format]):
            raise UnsupportedAudioFile(f"The file content is not {audio_format.value} audio.")
        length = getattr(audio.info, "length", None)
        duration = float(length) if isinstance(length, (int, float)) and length > 0 else None
        return AudioProbe(audio_format=audio_format, duration_seconds=duration)

    def read_tags(self, path: str) -> EmbeddedTags:
        try:
            audio = _load(path)
        except UnsupportedAudioFile as error:
            raise TagReadError("The file's tags could not be read.") from error
        if audio is None:
            raise TagReadError("The file's tags could not be read.")
        if audio.tags is None:
            return EmbeddedTags()
        try:
            return embedded_tags_from(audio.tags)
        except Exception as error:  # a malformed tag value must not stop the import
            raise TagReadError("The file's tags could not be read.") from error
