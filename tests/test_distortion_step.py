"""Tests for the `distortion` Effect Step.

Added after real-hardware feedback that a re-tuned Magos (ADR 0005)
sounded "much better... but lacking richness" -- direct FFT harmonic-
series comparison against reference audio confirmed `ring_mod`/
`bitcrush` alone weren't generating enough NEW harmonic content on real
(quiet) voice input. `distortion` (via `pedalboard.Distortion`,
waveshaping/saturation) is a genuinely different grit source: it
generates harmonics through a nonlinear transfer function, rather than
redistributing (`ring_mod`) or quantizing (`bitcrush`) whatever harmonic
content the input already has.

Verified here by feeding a PURE sine tone (a signal with, by
construction, zero energy at any harmonic of itself) through a compiled
`distortion` step and confirming harmonic energy appears where there
was none before -- the direct, unambiguous signature of waveshaping
distortion actually generating new harmonic content, not just
redistributing existing energy the way `ring_mod` does.
"""
import numpy as np

from voice_engine.engine import CompileChain, ProcessChain
from voice_engine.voice import EffectStep


def test_DistortionStepAddsHarmonicsToAPureSineTone() -> None:
    sampleRate = 22050
    frameCount = sampleRate  # 1 second, for clean FFT bin resolution
    frequency = 220.0
    amplitude = 0.3  # representative of a realistic, non-full-scale level

    time = np.arange(frameCount, dtype=np.float32) / sampleRate
    sineWave = (amplitude * np.sin(2 * np.pi * frequency * time)).astype(np.float32)
    block = sineWave.reshape(-1, 1)

    chain = [EffectStep(type="distortion", params={"drive_db": 40})]
    compiledChain = CompileChain(chain, sampleRate)
    result = ProcessChain(compiledChain, block)

    assert result.dtype == np.float32
    assert result.shape == block.shape

    freqs = np.fft.rfftfreq(frameCount, 1 / sampleRate)
    inputSpectrum = np.abs(np.fft.rfft(block[:, 0]))
    outputSpectrum = np.abs(np.fft.rfft(result[:, 0]))

    thirdHarmonicBin = np.argmin(np.abs(freqs - 3 * frequency))

    # A pure sine has (up to floating-point/windowing noise) no energy at
    # its own 3rd harmonic; distortion's whole point is to put real
    # energy there.
    assert outputSpectrum[thirdHarmonicBin] > 50 * inputSpectrum[thirdHarmonicBin]


def test_DistortionStepSelfBoundsOutputNearFullScale() -> None:
    # pedalboard.Distortion's waveshaping self-bounds its OWN output even
    # at high drive (confirmed via prototyping: peak <= 1.0 in isolation
    # regardless of drive_db) -- the real clipping risk this project
    # cares about (see CompileDistortionStep's docstring) is from LATER
    # steps adding further gain on top of an already near-full-scale
    # distorted signal, not from this step alone.
    sampleRate = 22050
    time = np.arange(sampleRate, dtype=np.float32) / sampleRate
    loudSineWave = (0.9 * np.sin(2 * np.pi * 220 * time)).astype(np.float32)
    block = loudSineWave.reshape(-1, 1)

    chain = [EffectStep(type="distortion", params={"drive_db": 60})]
    compiledChain = CompileChain(chain, sampleRate)
    result = ProcessChain(compiledChain, block)

    assert np.max(np.abs(result)) <= 1.0 + 1e-3
