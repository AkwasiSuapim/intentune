"""MutagenAudioInspector: validation by content, durations, and tag mapping for each tag system."""

import pytest
from mutagen._vorbis import VCommentDict
from mutagen.id3 import ID3, TCON, TDRC, TIT2, TPE1
from mutagen.mp4 import MP4Tags

from src.intentune.adapters.mutagen_audio import MutagenAudioInspector, embedded_tags_from
from src.intentune.domain.library import AudioFormat, EmbeddedTags, TagReadError, UnsupportedAudioFile


@pytest.fixture
def inspector():
    return MutagenAudioInspector()


@pytest.mark.parametrize(
    "kind, filename, audio_format, duration",
    [
        ("mp3", "a.mp3", AudioFormat.MP3, 1.045),
        ("wav", "a.wav", AudioFormat.WAV, 0.5),
        ("flac", "a.flac", AudioFormat.FLAC, 2.0),
    ],
)
def test_probe_confirms_the_format_and_reads_the_duration(inspector, audio, tmp_path, kind, filename, audio_format, duration):
    path = getattr(audio, kind)(tmp_path / filename)

    probe = inspector.probe(str(path), audio_format)

    assert probe.audio_format is audio_format
    assert probe.duration_seconds == pytest.approx(duration, abs=0.01)


def test_probe_rejects_text_with_an_audio_extension(inspector, tmp_path):
    path = tmp_path / "fake.mp3"
    path.write_text("not audio at all\n" * 50, encoding="utf-8")

    with pytest.raises(UnsupportedAudioFile):
        inspector.probe(str(path), AudioFormat.MP3)


@pytest.mark.parametrize("claimed", [AudioFormat.OGG, AudioFormat.FLAC, AudioFormat.M4A])
def test_probe_rejects_content_that_does_not_match_the_extension(inspector, audio, tmp_path, claimed):
    path = audio.mp3(tmp_path / f"mislabeled.{claimed.extension}")

    with pytest.raises(UnsupportedAudioFile):
        inspector.probe(str(path), claimed)


def test_probe_reports_an_unreadable_file_as_os_error(inspector, tmp_path):
    with pytest.raises(OSError):
        inspector.probe(str(tmp_path / "missing.flac"), AudioFormat.FLAC)


def test_empty_file_is_unsupported(inspector, tmp_path):
    path = tmp_path / "empty.wav"
    path.write_bytes(b"")

    with pytest.raises(UnsupportedAudioFile):
        inspector.probe(str(path), AudioFormat.WAV)


@pytest.mark.parametrize("kind, filename", [("mp3", "a.mp3"), ("wav", "a.wav")])
def test_read_tags_from_id3(inspector, audio, tmp_path, kind, filename):
    path = getattr(audio, kind)(
        tmp_path / filename, title="Song", artist=["A", "B"], album="Album", date="2019-05-03", genre=["(13)", "Rock; Indie"]
    )

    tags = inspector.read_tags(str(path))

    assert tags == EmbeddedTags(title="Song", artist="A, B", album="Album", year=2019, genres=("Pop", "Rock", "Indie"))


def test_read_tags_from_vorbis_comments(inspector, audio, tmp_path):
    path = audio.flac(tmp_path / "a.flac", TITLE="Flac Song", artist="Someone", date="1999", genre=["Jazz", "Blues"])

    assert inspector.read_tags(str(path)) == EmbeddedTags(title="Flac Song", artist="Someone", year=1999, genres=("Jazz", "Blues"))


@pytest.mark.parametrize("kind, filename", [("mp3", "a.mp3"), ("wav", "a.wav"), ("flac", "a.flac")])
def test_a_file_without_tags_has_empty_tags(inspector, audio, tmp_path, kind, filename):
    path = getattr(audio, kind)(tmp_path / filename)

    assert inspector.read_tags(str(path)) == EmbeddedTags()


def test_read_tags_of_invalid_audio_is_a_tag_read_error(inspector, tmp_path):
    path = tmp_path / "fake.mp3"
    path.write_text("not audio", encoding="utf-8")

    with pytest.raises(TagReadError):
        inspector.read_tags(str(path))


def test_mp4_atoms_map_to_embedded_tags():
    tags = MP4Tags()
    tags["\xa9nam"] = ["Title"]
    tags["\xa9ART"] = ["Artist"]
    tags["\xa9alb"] = ["Album"]
    tags["\xa9day"] = ["2020-01-01T00:00:00Z"]
    tags["\xa9gen"] = ["Soul"]

    assert embedded_tags_from(tags) == EmbeddedTags(title="Title", artist="Artist", album="Album", year=2020, genres=("Soul",))


def test_vorbis_comment_keys_are_case_insensitive():
    tags = VCommentDict()
    tags["TITLE"] = ["Upper"]
    tags["Genre"] = ["Ambient"]

    assert embedded_tags_from(tags) == EmbeddedTags(title="Upper", genres=("Ambient",))


def test_id3_without_optional_frames():
    tags = ID3()
    tags.add(TIT2(encoding=3, text=["Only a title"]))

    assert embedded_tags_from(tags) == EmbeddedTags(title="Only a title")


def test_id3_date_frames_with_only_a_year():
    tags = ID3()
    tags.add(TPE1(encoding=3, text=["Artist"]))
    tags.add(TDRC(encoding=3, text=["1987"]))
    tags.add(TCON(encoding=3, text=["Electronic"]))

    assert embedded_tags_from(tags) == EmbeddedTags(artist="Artist", year=1987, genres=("Electronic",))
