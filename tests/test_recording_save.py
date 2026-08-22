"""Tests for SaveRecordingWav (voice_engine/recording.py) -- concatenates
a recording's buffered blocks into a 16-bit PCM WAV file (not tied to a
SLICES.md slice; added for the Voice A/B testing workflow).
"""
import wave
from pathlib import Path

import numpy as np

from voice_engine.recording import SaveRecordingWav


def test_SaveRecordingWavWritesConcatenatedBlocksAtCorrectSampleRate(tmp_path: Path) -> None:
    sampleRate = 22050
    firstBlock = np.zeros((100, 1), dtype=np.float32)
    secondBlock = np.zeros((50, 1), dtype=np.float32)
    filePath = tmp_path / "recording.wav"

    SaveRecordingWav([firstBlock, secondBlock], sampleRate, str(filePath))

    with wave.open(str(filePath), "rb") as wavFile:
        assert wavFile.getnchannels() == 1
        assert wavFile.getsampwidth() == 2
        assert wavFile.getframerate() == sampleRate
        assert wavFile.getnframes() == 150


def test_SaveRecordingWavRoundTripsAmplitudeApproximately(tmp_path: Path) -> None:
    sampleRate = 22050
    time = np.arange(sampleRate, dtype=np.float32) / sampleRate
    sineWave = (0.5 * np.sin(2 * np.pi * 220 * time)).astype(np.float32).reshape(-1, 1)
    filePath = tmp_path / "recording.wav"

    SaveRecordingWav([sineWave], sampleRate, str(filePath))

    with wave.open(str(filePath), "rb") as wavFile:
        rawFrames = wavFile.readframes(wavFile.getnframes())
    readBackInt16 = np.frombuffer(rawFrames, dtype=np.int16)
    readBackFloat = readBackInt16.astype(np.float32) / 32767.0

    # int16 quantization introduces small error; the round-tripped signal
    # should still closely match the original.
    np.testing.assert_allclose(readBackFloat, sineWave[:, 0], atol=1e-3)


def test_SaveRecordingWavWithNoBlocksWritesAnEmptyValidWavFile(tmp_path: Path) -> None:
    filePath = tmp_path / "recording.wav"

    SaveRecordingWav([], 22050, str(filePath))

    with wave.open(str(filePath), "rb") as wavFile:
        assert wavFile.getnframes() == 0


def test_SaveRecordingWavClampsOutOfRangeSamples(tmp_path: Path) -> None:
    overScaleBlock = np.array([[2.0], [-2.0]], dtype=np.float32)
    filePath = tmp_path / "recording.wav"

    SaveRecordingWav([overScaleBlock], 22050, str(filePath))

    with wave.open(str(filePath), "rb") as wavFile:
        rawFrames = wavFile.readframes(wavFile.getnframes())
    readBackInt16 = np.frombuffer(rawFrames, dtype=np.int16)

    assert readBackInt16[0] == 32767
    assert readBackInt16[1] == -32767
