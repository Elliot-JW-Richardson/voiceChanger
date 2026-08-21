"""Tests for the distortion/bitcrush Effect Step (Slice 20).

Verification (from SLICES.md, Slice 20):
- Given a chain containing a bitcrush Effect Step set to a reduced bit
  depth
- When a smooth block of audio is processed through it
- Then the output contains only the limited number of distinct sample
  values that bit depth allows, confirming quantization occurred

Verified by generating a smooth sine wave (many thousands of distinct
amplitude values across a continuous [-1, 1] range) and running it
through a compiled bitcrush step at a low bit depth. Empirically (see
the exploration behind this test), `pedalboard.Bitcrush` quantizes
across the full [-1, 1] range in steps of `1 / 2 ** bit_depth`, which
produces `2 * 2 ** bit_depth + 1` distinct levels, not the naively
expected `2 ** bit_depth` (that count only covers one side of zero) --
this test asserts against that empirically observed ceiling (with a
small margin) rather than assuming the naive count, and separately
asserts the output's distinct-value count collapses drastically
relative to the smooth input's, which is the actual point of "grit via
quantization" this slice is verifying.
"""
import numpy as np

from voice_engine.engine import CompileChain, ProcessChain
from voice_engine.voice import EffectStep


def test_BitcrushStepQuantizesSmoothSignalToFewDistinctValues() -> None:
    sampleRate = 48000
    durationSeconds = 1.0
    frameCount = int(sampleRate * durationSeconds)
    inputFrequency = 220.0
    bitDepth = 3

    time = np.arange(frameCount, dtype=np.float32) / sampleRate
    sineWave = np.sin(2 * np.pi * inputFrequency * time).astype(np.float32)
    # Block shape/dtype matches sounddevice's indata/outdata convention:
    # float32, (frames, channels) — see tests/test_engine.py.
    block = sineWave.reshape(-1, 1)
    distinctInputValues = len(np.unique(block))

    chain = [EffectStep(type="bitcrush", params={"bit_depth": bitDepth})]
    compiledChain = CompileChain(chain, sampleRate)
    result = ProcessChain(compiledChain, block)

    assert result.dtype == np.float32
    assert result.shape == block.shape

    distinctOutputValues = len(np.unique(result))

    # The smooth sine wave, sampled at 48kHz for a full second, has many
    # thousands of distinct amplitude values -- confirm the input really
    # is "smooth" before checking that bitcrush collapses it.
    assert distinctInputValues > 1000

    # Empirically, pedalboard's Bitcrush quantizes across the whole
    # [-1, 1] range in steps of 1 / 2 ** bit_depth, producing at most
    # 2 * 2 ** bit_depth + 1 distinct levels (a small margin is added
    # for floating-point boundary noise).
    maxExpectedLevels = 2 * (2 ** bitDepth) + 1
    assert distinctOutputValues <= maxExpectedLevels + 2

    # The key point: quantization visibly occurred -- drastically fewer
    # distinct values than the smooth input had.
    assert distinctOutputValues < distinctInputValues / 100
