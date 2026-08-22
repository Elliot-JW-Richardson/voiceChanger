"""Tests for the `gain` Effect Step.

Added after real-hardware measurement (comparing recordings of the
retuned Magos, its distortion variants, and reference audio, all of the
same spoken content) found the biggest measured gap between Magos and
the reference target was LOUDNESS (~12x RMS), not spectral shape --
see voice_engine/engine.py's CompileGainStep docstring. `gain` is a
plain linear level boost (pedalboard.Gain, no waveshaping), unlike
`distortion` which also reshapes the waveform.
"""
import numpy as np

from voice_engine.engine import CompileChain, ProcessChain
from voice_engine.voice import EffectStep


def test_GainStepIncreasesRmsBySpecifiedAmount() -> None:
    sampleRate = 22050
    time = np.arange(sampleRate, dtype=np.float32) / sampleRate
    quietAmplitude = 0.05  # representative of this project's known-quiet mic input
    block = (quietAmplitude * np.sin(2 * np.pi * 220 * time)).astype(np.float32).reshape(-1, 1)

    gainDb = 12.0
    chain = [EffectStep(type="gain", params={"gain_db": gainDb})]
    compiledChain = CompileChain(chain, sampleRate)
    result = ProcessChain(compiledChain, block)

    assert result.dtype == np.float32
    assert result.shape == block.shape

    expectedLinearGain = 10 ** (gainDb / 20.0)
    inputRms = np.sqrt(np.mean(block ** 2))
    outputRms = np.sqrt(np.mean(result ** 2))
    np.testing.assert_allclose(outputRms / inputRms, expectedLinearGain, rtol=0.05)


def test_GainStepDoesNotReshapeTheWaveform() -> None:
    # Unlike `distortion`, a plain gain step should NOT add new harmonic
    # content to a pure sine tone -- it should stay a pure sine, just
    # louder, confirming this is linear amplification, not waveshaping.
    sampleRate = 22050
    frameCount = sampleRate
    frequency = 220.0
    time = np.arange(frameCount, dtype=np.float32) / sampleRate
    block = (0.1 * np.sin(2 * np.pi * frequency * time)).astype(np.float32).reshape(-1, 1)

    chain = [EffectStep(type="gain", params={"gain_db": 15.0})]
    compiledChain = CompileChain(chain, sampleRate)
    result = ProcessChain(compiledChain, block)

    freqs = np.fft.rfftfreq(frameCount, 1 / sampleRate)
    inputSpectrum = np.abs(np.fft.rfft(block[:, 0]))
    outputSpectrum = np.abs(np.fft.rfft(result[:, 0]))
    thirdHarmonicBin = np.argmin(np.abs(freqs - 3 * frequency))

    # A pure sine has no energy at its own 3rd harmonic before OR after
    # a plain gain boost.
    assert outputSpectrum[thirdHarmonicBin] < 10 * inputSpectrum[thirdHarmonicBin] + 1e-3
