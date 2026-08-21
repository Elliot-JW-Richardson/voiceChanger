"""Tests for the pitch shift Effect Step (Slice 11).

Verification (from SLICES.md, Slice 11):
- Given a chain containing a pitch-shift Effect Step set to a number of
  semitones
- When a block of audio is processed through it
- Then the output audio's pitch is shifted by that amount

Verified in the frequency domain: a pure sine wave of a known frequency
is run through a compiled pitch-shift step, and the dominant frequency of
the output (found via `numpy.fft.rfft`) is checked against the
expected shifted frequency (`inputFrequency * 2 ** (semitones / 12)`).
A block considerably longer than the live callback's BLOCKSIZE (1024,
see app.py) is used for adequate FFT bin resolution --
`ProcessChain`/`CompileChain` aren't hardcoded to any particular block
size, so this is safe to do outside the real-time path.
"""
import numpy as np

from voice_engine.engine import CompileChain, ProcessChain
from voice_engine.voice import EffectStep


def test_PitchShiftStepShiftsSineWaveFrequency() -> None:
    sampleRate = 48000
    durationSeconds = 2.0
    frameCount = int(sampleRate * durationSeconds)
    inputFrequency = 220.0
    semitones = -6

    time = np.arange(frameCount, dtype=np.float32) / sampleRate
    sineWave = np.sin(2 * np.pi * inputFrequency * time).astype(np.float32)
    # Block shape/dtype matches sounddevice's indata/outdata convention:
    # float32, (frames, channels) — see tests/test_engine.py.
    block = sineWave.reshape(-1, 1)

    chain = [EffectStep(type="pitch_shift", params={"semitones": semitones})]
    compiledChain = CompileChain(chain, sampleRate)
    result = ProcessChain(compiledChain, block)

    assert result.dtype == np.float32
    assert result.shape == block.shape

    spectrum = np.fft.rfft(result[:, 0])
    frequencyBins = np.fft.rfftfreq(frameCount, d=1.0 / sampleRate)
    dominantFrequency = frequencyBins[np.argmax(np.abs(spectrum))]

    expectedFrequency = inputFrequency * 2 ** (semitones / 12)
    assert abs(dominantFrequency - expectedFrequency) < 3.0


def test_PitchShiftStepStaysCorrectAcrossRepeatedCallsOnTheSameCompiledInstance() -> None:
    # Regression test: CompilePitchShiftStep must build its Pedalboard
    # once and reuse it across calls, not rebuild it per call (which was
    # a real bug -- see git history -- causing audible underflow/overflow
    # in the live audio callback). This calls the SAME compiled step
    # object multiple times in a row and checks it remains correct each
    # time, guarding against that regression.
    sampleRate = 48000
    durationSeconds = 2.0
    frameCount = int(sampleRate * durationSeconds)
    inputFrequency = 220.0
    semitones = -6

    time = np.arange(frameCount, dtype=np.float32) / sampleRate
    sineWave = np.sin(2 * np.pi * inputFrequency * time).astype(np.float32)
    block = sineWave.reshape(-1, 1)

    chain = [EffectStep(type="pitch_shift", params={"semitones": semitones})]
    compiledStep = CompileChain(chain, sampleRate)[0]

    expectedFrequency = inputFrequency * 2 ** (semitones / 12)
    frequencyBins = np.fft.rfftfreq(frameCount, d=1.0 / sampleRate)

    for _ in range(3):
        result = compiledStep(block)
        spectrum = np.fft.rfft(result[:, 0])
        dominantFrequency = frequencyBins[np.argmax(np.abs(spectrum))]
        assert abs(dominantFrequency - expectedFrequency) < 3.0
