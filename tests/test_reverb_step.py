"""Tests for the reverb Effect Step (Slice 24).

Verification (from SLICES.md, Slice 24):
- Given a chain containing a reverb Effect Step with a non-zero wet level
- When a short impulse of audio is processed through it
- Then the output contains a decay tail extending beyond the impulse's
  original position

Verified in the time domain: a block is built as a single-sample impulse
(one full-scale sample) followed by silence. The block is run through a
compiled `reverb` Effect Step with a non-zero `wet_level` and a large
`room_size` (for a long, easily-detectable tail). The acceptance
criteria only requires a decay tail extending beyond the impulse's
original position WITHIN this one `process()` call -- not carrying
across separate calls/block boundaries, which `reset=True` doesn't
support anyway (see CLAUDE.md's Real-time performance notes, point 3,
and CompilePitchShiftStep's docstring for the established precedent on
this project's accepted `reset=True` limitation). So this test processes
the impulse and its silent tail in a single block, then checks that the
region well after the impulse -- silent in the input -- has clearly
non-negligible energy in the output, confirming reverb decay is present
there.
"""
import numpy as np

from voice_engine.engine import CompileChain, ProcessChain
from voice_engine.voice import EffectStep


def test_ReverbStepAddsDecayTailAfterImpulse() -> None:
    sampleRate = 48000
    durationSeconds = 1.0
    frameCount = int(sampleRate * durationSeconds)
    impulseIndex = 0
    tailStartIndex = 2000  # well after the impulse

    impulse = np.zeros(frameCount, dtype=np.float32)
    impulse[impulseIndex] = 1.0
    # Block shape/dtype matches sounddevice's indata/outdata convention:
    # float32, (frames, channels) — see tests/test_engine.py.
    block = impulse.reshape(-1, 1)

    # Confirm the input really is silent after the impulse before
    # checking that reverb adds a tail there.
    inputTailMagnitude = np.max(np.abs(block[tailStartIndex:, 0]))
    assert inputTailMagnitude == 0.0

    chain = [
        EffectStep(
            type="reverb",
            params={"wet_level": 1.0, "room_size": 1.0},
        )
    ]
    compiledChain = CompileChain(chain, sampleRate)
    result = ProcessChain(compiledChain, block)

    assert result.dtype == np.float32
    assert result.shape == block.shape

    # The actual acceptance criteria: the region well after the
    # impulse's original position, silent in the input, must have
    # clearly non-negligible energy in the output -- a decay tail.
    outputTailMagnitude = np.max(np.abs(result[tailStartIndex:, 0]))
    assert outputTailMagnitude > 1e-4
