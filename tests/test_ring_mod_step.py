"""Tests for the ring modulation Effect Step (Slice 19).

Verification (from SLICES.md, Slice 19):
- Given a chain containing a ring-modulation Effect Step
- When two consecutive blocks of audio are processed through it
- Then the oscillator's phase at the start of the second block continues
  seamlessly from where it left off at the end of the first, with no
  discontinuity at the boundary

Ring modulation (see CONTEXT.md's Effect palette entry) multiplies the
input signal, sample by sample, by a sine wave oscillator at some carrier
frequency: output[i] = input[i] * sin(2*pi*frequency*t[i]), where t[i] is
a continuously-advancing time value in seconds -- NOT reset to 0 at the
start of every block.

This is tested by isolating the oscillator itself rather than checking
plausibility: a CONSTANT input block (all 1.0s) is fed through the SAME
compiled step TWICE in a row (two separate calls, simulating two
consecutive audio callback invocations). Because multiplying by 1.0
leaves the oscillator's own waveform unchanged, the two outputs,
concatenated, must exactly match a single continuous oscillator computed
all at once for the combined duration. This directly proves phase
continuity across the block boundary -- a single-block inspection or an
FFT-based frequency check (the pattern used for pitch shift's frequency
correctness, a different property) would not catch a phase reset.
"""
import numpy as np

from voice_engine.engine import CompileChain, ProcessChain
from voice_engine.voice import EffectStep


def test_RingModulationOscillatorPhaseContinuousAcrossBlocks() -> None:
    sampleRate = 48000
    frequency = 30.0
    framesPerBlock = 1024

    firstBlock = np.ones((framesPerBlock, 1), dtype=np.float32)
    secondBlock = np.ones((framesPerBlock, 1), dtype=np.float32)

    chain = [EffectStep(type="ring_mod", params={"frequency": frequency})]
    compiledStep = CompileChain(chain, sampleRate)[0]

    firstResult = ProcessChain([compiledStep], firstBlock)
    secondResult = ProcessChain([compiledStep], secondBlock)

    actualConcatenated = np.concatenate([firstResult[:, 0], secondResult[:, 0]])

    totalFrames = framesPerBlock * 2
    time = np.arange(totalFrames, dtype=np.float64) / sampleRate
    expectedConcatenated = np.sin(2 * np.pi * frequency * time)

    np.testing.assert_allclose(actualConcatenated, expectedConcatenated, atol=1e-4)
