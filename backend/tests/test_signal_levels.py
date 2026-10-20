"""SignalLevelAnalyzer: exact level measurements of real encoded audio, and safe failure on bad input."""

import math

import numpy as np
import pytest
import soundfile

from src.intentune.adapters.signal_levels import ANALYZER_NAME, SignalLevelAnalyzer
from src.intentune.domain.analysis import AudioDecodeError, FeatureName
from src.intentune.domain.library import AudioFormat

_AMPLITUDE = 0.5
_SINE_RMS = _AMPLITUDE / math.sqrt(2)


@pytest.fixture
def analyzer():
    return SignalLevelAnalyzer()


def _measure(analyzer, path, audio_format):
    return analyzer.analyze(str(path), audio_format).values


def test_identity_names_the_analyzer_and_decoder_version(analyzer):
    assert analyzer.identity.name == ANALYZER_NAME
    assert analyzer.identity.version == f"1+libsndfile-{soundfile.__libsndfile_version__}"
    assert analyzer.identity.key == f"{ANALYZER_NAME}@{analyzer.identity.version}"


def test_supports_every_allowlisted_format_libsndfile_decodes(analyzer):
    assert {audio_format for audio_format in AudioFormat if analyzer.supports(audio_format)} == {
        AudioFormat.MP3,
        AudioFormat.FLAC,
        AudioFormat.OGG,
        AudioFormat.OPUS,
        AudioFormat.WAV,
    }
    assert not analyzer.supports(AudioFormat.M4A)


@pytest.mark.parametrize("filename, audio_format", [("tone.wav", AudioFormat.WAV), ("tone.flac", AudioFormat.FLAC)])
def test_lossless_formats_measure_exactly(analyzer, audio, tmp_path, filename, audio_format):
    values = _measure(analyzer, audio.tone(tmp_path / filename, amplitude=_AMPLITUDE, seconds=1.0), audio_format)

    assert values[FeatureName.DECODED_DURATION_SECONDS] == 1.0
    assert values[FeatureName.SAMPLE_PEAK] == pytest.approx(_AMPLITUDE, abs=1e-3)
    assert values[FeatureName.RMS_LEVEL] == pytest.approx(_SINE_RMS, abs=1e-3)


@pytest.mark.parametrize(
    "filename, audio_format",
    [("tone.ogg", AudioFormat.OGG), ("tone.opus", AudioFormat.OPUS), ("tone.mp3", AudioFormat.MP3)],
)
def test_lossy_formats_are_measured_as_decoded(analyzer, audio, tmp_path, filename, audio_format):
    """A lossy codec changes the samples (Opus overshoots this tone's abrupt start to a peak near 0.67).

    The analyzer measures what the decoder produces. Its block-by-block results
    must equal a whole-file computation on the same decoded samples, and stay
    plausibly close to the source tone.
    """
    path = audio.tone(tmp_path / filename, amplitude=_AMPLITUDE, seconds=1.0)
    decoded, sample_rate = soundfile.read(str(path), dtype="float64", always_2d=True)

    values = _measure(analyzer, path, audio_format)

    assert values[FeatureName.DECODED_DURATION_SECONDS] == decoded.shape[0] / sample_rate
    assert values[FeatureName.SAMPLE_PEAK] == pytest.approx(float(np.max(np.abs(decoded))), rel=1e-12)
    assert values[FeatureName.RMS_LEVEL] == pytest.approx(float(np.sqrt(np.mean(decoded ** 2))), rel=1e-9)
    assert values[FeatureName.DECODED_DURATION_SECONDS] == pytest.approx(1.0, abs=0.06)
    assert values[FeatureName.RMS_LEVEL] == pytest.approx(_SINE_RMS, abs=0.03)


def test_digital_silence_measures_zero(analyzer, audio, tmp_path):
    values = _measure(analyzer, audio.tone(tmp_path / "silence.flac", amplitude=0.0, seconds=0.5), AudioFormat.FLAC)

    assert values[FeatureName.SAMPLE_PEAK] == 0.0
    assert values[FeatureName.RMS_LEVEL] == 0.0
    assert values[FeatureName.DECODED_DURATION_SECONDS] == 0.5


def test_levels_scale_with_amplitude(analyzer, audio, tmp_path):
    quiet = _measure(analyzer, audio.tone(tmp_path / "quiet.wav", amplitude=0.1), AudioFormat.WAV)
    loud = _measure(analyzer, audio.tone(tmp_path / "loud.wav", amplitude=0.8), AudioFormat.WAV)

    assert loud[FeatureName.SAMPLE_PEAK] / quiet[FeatureName.SAMPLE_PEAK] == pytest.approx(8.0, rel=1e-2)
    assert loud[FeatureName.RMS_LEVEL] / quiet[FeatureName.RMS_LEVEL] == pytest.approx(8.0, rel=1e-2)


def test_the_peak_is_found_beyond_the_first_read_block(analyzer, audio, tmp_path):
    path = audio.tone(tmp_path / "spike.wav", amplitude=0.1, seconds=3.0, spike=(100_000, 0.9))  # blocks are 65,536 frames

    values = _measure(analyzer, path, AudioFormat.WAV)

    assert values[FeatureName.SAMPLE_PEAK] == pytest.approx(0.9, abs=1e-3)
    assert values[FeatureName.DECODED_DURATION_SECONDS] == 3.0


def test_mono_and_stereo_copies_of_a_signal_measure_the_same(analyzer, audio, tmp_path):
    mono = _measure(analyzer, audio.tone(tmp_path / "mono.wav", channels=1), AudioFormat.WAV)
    stereo = _measure(analyzer, audio.tone(tmp_path / "stereo.wav", channels=2), AudioFormat.WAV)

    assert mono == stereo


@pytest.mark.parametrize("content", [b"not audio at all" * 100, b""])
def test_undecodable_content_raises_a_decode_error_without_the_path(analyzer, tmp_path, content):
    folder = tmp_path / "private-folder-name"
    folder.mkdir()
    path = folder / "broken.flac"
    path.write_bytes(content)

    with pytest.raises(AudioDecodeError) as raised:
        analyzer.analyze(str(path), AudioFormat.FLAC)

    assert "private-folder-name" not in str(raised.value)
    assert "broken.flac" not in str(raised.value)


def test_an_unreadable_file_raises_os_error(analyzer, tmp_path):
    with pytest.raises(OSError):
        analyzer.analyze(str(tmp_path / "missing.flac"), AudioFormat.FLAC)
