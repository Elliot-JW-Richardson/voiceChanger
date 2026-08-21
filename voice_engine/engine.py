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
"""
from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray
from pedalboard import Pedalboard, PitchShift

from voice_engine.voice import EffectStep

AudioBlock = NDArray[np.float32]
# The runtime, callable form of an Effect Step, distinct from the
# declarative Effect Step data (type + params) defined in the Voice Bank
# (see CONTEXT.md) — later slices bridge from one to the other.
CompiledEffectStep = Callable[[AudioBlock], AudioBlock]


def CompilePitchShiftStep(step: EffectStep, sampleRate: int) -> CompiledEffectStep:
    """Compile a `pitch_shift` Effect Step into a callable that runs a
    block through `pedalboard.PitchShift`.

    `pedalboard.Pedalboard.process()` needs a sample rate to shift pitch
    correctly, so `sampleRate` is baked into the returned closure at
    compile time. No cross-block streaming state is kept (see SLICES.md,
    Slice 11's scope notes) -- each call builds a fresh `Pedalboard`,
    which is simple and sufficient since pitch shift has no phase-
    continuity requirement across blocks (unlike ring modulation,
    Slice 13).

    This project's `AudioBlock` convention -- (frames, channels) float32,
    matching sounddevice's indata/outdata -- is also the shape
    `pedalboard.Pedalboard.process()` auto-detects as (samples, channels)
    for mono (channels=1, the only case this project uses), so no shape
    conversion is needed either way: the block goes in and comes back out
    in the same (frames, channels) layout.
    """
    semitones = step.params["semitones"]

    def PitchShiftStep(block: AudioBlock) -> AudioBlock:
        pedalboardChain = Pedalboard([PitchShift(semitones=semitones)])
        shiftedBlock = pedalboardChain.process(block, sampleRate)
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
