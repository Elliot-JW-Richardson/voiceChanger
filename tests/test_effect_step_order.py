"""Tests for Effect Steps composing in declared order (Slice 21).

Verification (from SLICES.md, Slice 21):
- Given a chain declaring a ring-modulation step followed by a bitcrush step
- When a block of audio is processed through it
- Then the result matches applying ring modulation first and bitcrush
  second, and differs from applying them in the reverse order

`ProcessChain` (voice_engine/engine.py) is a simple `for step in steps:
block = step(block)` loop, order-preserving by construction since Slice 1,
and `CompileChain` dispatches each Effect Step in the declared list order.
This slice is a regression test confirming that already-correct behavior,
not new implementation.

Ring modulation's compiled closure is STATEFUL (see
`CompileRingModStep`'s docstring: it advances an internal `phaseSeconds`
counter on every call via `nonlocal`), so the same compiled ring-mod step
must never be invoked twice across two different logical checks in this
test -- doing so would desync the phase between the two checks. To avoid
that, this test compiles the `[ring_mod, bitcrush]` chain THREE
independent times (three separate `CompileChain` calls, each producing
its own freshly-initialized ring-mod closure): once to get the actual
`ProcessChain` result, once to manually apply the two compiled steps by
hand for comparison, and once more (reversed) to prove order matters.

A real sine wave block is used (not all-zero/all-one data) so the two
orderings are actually likely to produce numerically different results --
ring-mod-then-bitcrush and bitcrush-then-ring-mod are not commutative
operations in general.
"""
import numpy as np

from voice_engine.engine import CompileChain, ProcessChain
from voice_engine.voice import EffectStep


def test_EffectStepsComposeInDeclaredOrder() -> None:
    sampleRate = 48000
    durationSeconds = 1.0
    frameCount = int(sampleRate * durationSeconds)
    inputFrequency = 220.0

    time = np.arange(frameCount, dtype=np.float32) / sampleRate
    sineWave = np.sin(2 * np.pi * inputFrequency * time).astype(np.float32)
    block = sineWave.reshape(-1, 1)

    ringModStep = EffectStep(type="ring_mod", params={"frequency": 30.0})
    bitcrushStep = EffectStep(type="bitcrush", params={"bit_depth": 3})
    declaredChain = [ringModStep, bitcrushStep]
    reversedChain = [bitcrushStep, ringModStep]

    # (a) Compile the declared-order chain once and run it through
    # ProcessChain -- this is the actual result under test.
    compiledDeclaredChain = CompileChain(declaredChain, sampleRate)
    actualResult = ProcessChain(compiledDeclaredChain, block)

    # (b) Compile the SAME declared-order chain a second, independent
    # time, and manually apply its two compiled steps in order by hand.
    # A fresh compile is required so this ring-mod closure's phase state
    # hasn't already been advanced by (a)'s call.
    manualCompiledChain = CompileChain(declaredChain, sampleRate)
    manualResult = manualCompiledChain[1](manualCompiledChain[0](block))

    np.testing.assert_array_equal(actualResult, manualResult)

    # (c) Compile the REVERSED chain independently and run it through
    # ProcessChain -- this must NOT match the declared-order result,
    # proving order genuinely affects the outcome.
    compiledReversedChain = CompileChain(reversedChain, sampleRate)
    reversedResult = ProcessChain(compiledReversedChain, block)

    assert not np.allclose(actualResult, reversedResult)
