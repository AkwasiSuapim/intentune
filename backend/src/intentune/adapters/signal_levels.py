"""AudioAnalyzer adapter: exact signal-level measurements of decoded audio (B3).

Measurements (analyzer revision 1), over every decoded sample of every channel:

- decoded_duration_seconds: decoded frames divided by the sample rate.
- sample_peak: the largest absolute sample value, as a fraction of digital
  full scale (1.0 is 0 dBFS). It is a sample peak, not a true (inter-sample)
  peak. Lossy decoders can produce values slightly above 1.0.
- rms_level: the root mean square of the sample values, as a fraction of
  full scale.

Levels are stored as linear fractions because digital silence has a defined
level (0.0) but no finite dBFS value. dBFS is 20·log10(value).

These are measurements of the signal, not perceptual or semantic features.
sample_peak and rms_level are not loudness in LUFS (ITU-R BS.1770 weighting
and gating are not applied), and none of these is "energy", "danceability",
or any other provider-style attribute (D21). Tempo, key, and onset estimates
are not produced: they are estimates whose accuracy Intentune cannot yet
evaluate.

Decoding uses libsndfile through soundfile: WAV, FLAC, Ogg Vorbis, Opus, and
MP3. libsndfile cannot decode M4A (AAC/ALAC), so M4A tracks are skipped.
Lossy formats decode to slightly different samples with different decoder
builds, so the libsndfile version is part of the analyzer version, and
upgrading it re-analyzes the library. Audio is read in fixed-size blocks, so
memory use does not grow with track length.
"""

import math

import numpy as np
import soundfile

from src.intentune.domain.analysis import AnalysisResult, AnalyzerIdentity, AudioDecodeError, FeatureName
from src.intentune.domain.library import AudioFormat

ANALYZER_NAME = "intentune.signal-levels"
ANALYZER_REVISION = "1"

_SUPPORTED_FORMATS = frozenset({AudioFormat.MP3, AudioFormat.FLAC, AudioFormat.OGG, AudioFormat.OPUS, AudioFormat.WAV})
_BLOCK_FRAMES = 65536


class SignalLevelAnalyzer:
    def __init__(self) -> None:
        self._identity = AnalyzerIdentity(
            name=ANALYZER_NAME,
            version=f"{ANALYZER_REVISION}+libsndfile-{soundfile.__libsndfile_version__}",
        )

    @property
    def identity(self) -> AnalyzerIdentity:
        return self._identity

    def supports(self, audio_format: AudioFormat) -> bool:
        return AudioFormat(audio_format) in _SUPPORTED_FORMATS

    def analyze(self, path: str, audio_format: AudioFormat) -> AnalysisResult:
        # Python opens the file, so a read problem is an OSError (retryable).
        # Everything libsndfile reports is about the content (not retried).
        with open(path, "rb") as handle:
            try:
                frames, sample_rate, peak, sum_of_squares, samples = _measure(handle)
            except RuntimeError as error:  # soundfile.LibsndfileError is a RuntimeError
                detail = getattr(error, "error_string", None) or "unknown libsndfile error"
                raise AudioDecodeError(f"The audio could not be decoded: {detail}") from error

        if frames == 0 or sample_rate <= 0:
            raise AudioDecodeError("The file contains no audio samples.")
        rms = math.sqrt(sum_of_squares / samples)
        if not (math.isfinite(peak) and math.isfinite(rms)):
            raise AudioDecodeError("The decoded samples are not finite numbers.")
        return AnalysisResult(
            values={
                FeatureName.DECODED_DURATION_SECONDS: frames / sample_rate,
                FeatureName.SAMPLE_PEAK: peak,
                FeatureName.RMS_LEVEL: rms,
            }
        )


def _measure(handle):
    frames = 0
    samples = 0
    peak = 0.0
    sum_of_squares = 0.0
    with soundfile.SoundFile(handle) as audio:
        sample_rate = audio.samplerate
        for block in audio.blocks(blocksize=_BLOCK_FRAMES, dtype="float64", always_2d=True):
            if block.size == 0:
                continue
            frames += block.shape[0]
            samples += block.size
            peak = max(peak, float(np.max(np.abs(block))))
            sum_of_squares += float(np.dot(block.ravel(), block.ravel()))
    return frames, sample_rate, peak, sum_of_squares, samples
