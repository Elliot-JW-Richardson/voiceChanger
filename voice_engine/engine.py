"""Effect Engine: applies a Voice's ordered Effect Step chain to an audio block.

An Effect Step (see CONTEXT.md) is one entry in a DSP Voice's chain: an
effect type plus its parameters. A DSP Voice is an ordered list of Effect
Steps applied in sequence to each audio block.

`CompileChain` bridges a Voice's DECLARATIVE chain (`EffectStep` data --
see `voice_engine.voice`) to the compiled, callable form `ProcessChain`
expects. Slice 11 adds the first concrete Effect Step type, pitch shift
(via `pedalboard`), which needs the stream's sample rate to shift
correctly -- hence `CompileChain` takes `sampleRate` and bakes it into
the closures it builds for steps that need it. Remaining palette types
(ring modulation, distortion/bitcrush, EQ, reverb) arrive in later
slices, 13 onward, and still raise `NotImplementedError` until then.

IMPORTANT for anyone adding a new Effect Step type: any expensive setup
(e.g. constructing a `pedalboard.Pedalboard`/plugin instance) MUST happen
once inside the `Compile*Step` function, not inside the returned
`CompiledEffectStep` closure. The closure runs on the real-time audio
callback thread once per ~21ms block (BLOCKSIZE=1024 @ SAMPLE_RATE=48000)
-- doing expensive work there causes audible underflow/overflow (see the
bug this comment is fixing). Similarly, callers of `CompileChain` should
not call it fresh on every block either; use `CompiledChainCache` below
to recompile only when the active Voice actually changes.
"""
from collections.abc import Callable
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from pedalboard import Pedalboard, PitchShift

from voice_engine.voice import EffectStep, Voice

AudioBlock = NDArray[np.float32]
# The runtime, callable form of an Effect Step, distinct from the
# declarative Effect Step data (type + params) defined in the Voice Bank
# (see CONTEXT.md) — later slices bridge from one to the other.
CompiledEffectStep = Callable[[AudioBlock], AudioBlock]


def CompilePitchShiftStep(step: EffectStep, sampleRate: int) -> CompiledEffectStep:
    """Compile a `pitch_shift` Effect Step into a callable that runs a
    block through `pedalboard.PitchShift`.

    The `Pedalboard`/`PitchShift` instance is constructed ONCE here, at
    compile time, and reused for every subsequent block via the closure
    -- constructing it per-block (as an earlier version of this function
    did) was expensive enough to blow the real-time budget and cause
    audible underflow/overflow.

    `.process()` is called with the default `reset=True`: each block is
    treated as its own complete, independent signal, which is what
    guarantees the output is always the SAME LENGTH as the input block --
    a hard requirement here, since `AudioCallback` writes the result
    straight into a fixed-size `outdata` buffer via `outdata[:] = ...`.
    `reset=False` (pedalboard's true streaming mode, tried and reverted --
    see git history) holds samples back internally to reduce latency
    across many small calls, and returns a SHORTER block than it was
    given on the first call, which breaks that invariant. The trade-off
    of `reset=True` is that each block's pitch-shift processing doesn't
    carry state across the block boundary, which could in principle cause
    small block-edge artifacts -- not covered by this slice's acceptance
    criteria (see SLICES.md, Slice 11), unlike ring modulation's Slice 13,
    which explicitly tests phase continuity.

    This project's `AudioBlock` convention -- (frames, channels) float32,
    matching sounddevice's indata/outdata -- is also the shape
    `pedalboard.Pedalboard.process()` auto-detects as (samples, channels)
    for mono (channels=1, the only case this project uses), so no shape
    conversion is needed either way: the block goes in and comes back out
    in the same (frames, channels) layout.
    """
    semitones = step.params["semitones"]
    pedalboardChain = Pedalboard([PitchShift(semitones=semitones)])

    def PitchShiftStep(block: AudioBlock) -> AudioBlock:
        shiftedBlock = pedalboardChain.process(block, sampleRate, reset=True)
        return shiftedBlock.astype(np.float32)

    return PitchShiftStep


def CompileChain(chain: list[EffectStep], sampleRate: int) -> list[CompiledEffectStep]:
    """Compile a Voice's declarative Effect Step chain into the callable
    form `ProcessChain` expects.

    sampleRate: the audio stream's sample rate in Hz, needed by Effect
        Step types (e.g. pitch shift) whose underlying DSP depends on it.

    Dispatches by each step's `type`; `pitch_shift` is the only concrete
    type handled so far (Slice 11). Any other type raises
    `NotImplementedError`, exactly as before Slice 11 -- ring modulation,
    distortion/bitcrush, EQ, and reverb arrive in later slices (13, 14,
    17, 18).
    """
    compiledSteps: list[CompiledEffectStep] = []
    for step in chain:
        if step.type == "pitch_shift":
            compiledSteps.append(CompilePitchShiftStep(step, sampleRate))
        else:
            raise NotImplementedError(f"Unknown Effect Step type: {step.type}")
    return compiledSteps


class CompiledChainCache:
    """Caches the compiled chain for the most recently seen active Voice,
    recompiling only when the Voice actually changes (by id).

    `CompileChain` can be expensive (e.g. constructing a `pedalboard`
    plugin instance per Effect Step) -- calling it fresh on every audio
    block, as the live callback originally did, reintroduces the same
    real-time performance problem `CompilePitchShiftStep`'s docstring
    describes, just one layer up. This cache is what lets the audio
    callback call `CompileChain` effectively once per Voice selection
    instead of once per ~21ms block.
    """

    def __init__(self, sampleRate: int) -> None:
        self.sampleRate = sampleRate
        self.cachedVoiceId: Optional[str] = None
        self.cachedChain: list[CompiledEffectStep] = []

    def Get(self, voice: Voice) -> list[CompiledEffectStep]:
        if voice.id != self.cachedVoiceId:
            self.cachedChain = CompileChain(voice.chain, self.sampleRate)
            self.cachedVoiceId = voice.id
        return self.cachedChain


def ApplyMasterVolume(block: AudioBlock, level: int) -> AudioBlock:
    """Scale a block of audio by the Master Volume level (see CONTEXT.md's
    Master Volume entry and ADR 0002), clipping the result to the valid
    [-1.0, 1.0] audio range.

    level: a percentage, 0-200 (100 = unity gain, unchanged output),
        as tracked by `voice_engine.runtime.MasterVolumeHolder`.

    Deliberately separate from the Effect Step chain machinery above --
    Master Volume is a single global control applied AFTER a Voice's
    Effect Step chain, independent of which Voice is active; it is not
    itself an Effect Step and has no entry in `CompileChain`'s dispatch.

    Clipping (via `np.clip`) is what prevents boosting above 100% from
    pushing samples outside the range a speaker can represent -- without
    it, a loud block scaled above unity gain could produce values outside
    [-1.0, 1.0], causing digital distortion.
    """
    scaledBlock = block * (level / 100.0)
    return np.clip(scaledBlock, -1.0, 1.0).astype(np.float32)


def ProcessChain(steps: list[CompiledEffectStep], block: AudioBlock) -> AudioBlock:
    """Apply an ordered list of compiled Effect Steps to a block of audio.

    steps: ordered list of compiled Effect Steps. Each step must be
        callable, taking the current block and returning the next block.
        An empty list leaves the block unchanged (the Passthrough Voice).
    block: numpy float32 array shaped (frames, channels), matching the
        indata/outdata convention used by sounddevice's audio callback
        (see app.py's audio_callback).

    Returns the resulting block after applying every step in order.
    """
    for step in steps:
        block = step(block)
    return block
