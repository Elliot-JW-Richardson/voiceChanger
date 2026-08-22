"""Tests for the `limiter` Effect Step.

Added alongside `distortion` (see CompileDistortionStep's docstring):
distortion at the drive levels that meaningfully enrich harmonics on
real (quiet) voice input can leave a chain's output near full scale, and
any LATER step that adds further gain (e.g. `eq`'s shelf boost) can then
push a chain's output well past [-1.0, 1.0] -- confirmed via testing to
reach a peak of ~2.5 on real voice input. This can NOT be caught by
`ApplyMasterVolume`'s own Limiter downstream in `AudioCallback`, because
that one is bypassed entirely at the default 100% Master Volume level
(see `ApplyMasterVolume`'s docstring) -- a Voice's chain must be able to
bound itself explicitly.

Verified here by feeding a block that's deliberately already past
[-1.0, 1.0] (simulating what a `distortion` + gain-adding chain can
produce) through a compiled `limiter` step and confirming the output is
brought back within range.
"""
import numpy as np

from voice_engine.engine import CompileChain, ProcessChain
from voice_engine.voice import EffectStep


def test_LimiterStepBoundsAnOverScaleSignalWithinRange() -> None:
    sampleRate = 22050
    time = np.arange(sampleRate, dtype=np.float32) / sampleRate
    # Deliberately over full scale -- simulates what distortion + a later
    # gain-adding step (e.g. eq) can produce (see this file's docstring;
    # a peak of ~2.5 was observed in exactly that scenario during
    # prototyping).
    overScaleBlock = (2.5 * np.sin(2 * np.pi * 220 * time)).astype(np.float32).reshape(-1, 1)
    assert np.max(np.abs(overScaleBlock)) > 1.0

    chain = [EffectStep(type="limiter", params={"threshold_db": -1.0})]
    compiledChain = CompileChain(chain, sampleRate)
    result = ProcessChain(compiledChain, overScaleBlock)

    assert result.dtype == np.float32
    assert result.shape == overScaleBlock.shape
    assert np.max(np.abs(result)) <= 1.0


def test_LimiterStepLeavesAnAlreadyQuietSignalLargelyUnaffected() -> None:
    sampleRate = 22050
    time = np.arange(sampleRate, dtype=np.float32) / sampleRate
    quietBlock = (0.1 * np.sin(2 * np.pi * 220 * time)).astype(np.float32).reshape(-1, 1)

    chain = [EffectStep(type="limiter", params={"threshold_db": -1.0})]
    compiledChain = CompileChain(chain, sampleRate)
    result = ProcessChain(compiledChain, quietBlock)

    # A quiet signal well under the limiter's threshold should pass
    # through with only whatever gentle shaping the limiter's compressor
    # curve applies near the top of its range -- not be crushed down.
    assert np.max(np.abs(result)) > 0.08
