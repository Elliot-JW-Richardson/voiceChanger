"""Effect Engine: applies a Voice's ordered Effect Step chain to an audio block.

An Effect Step (see CONTEXT.md) is one entry in a DSP Voice's chain: an
effect type plus its parameters. A DSP Voice is an ordered list of Effect
Steps applied in sequence to each audio block.

This slice establishes only the chain-processing mechanism itself and
proves the empty-chain (Passthrough Voice) identity case: no Effect Step
types exist yet, so `steps` is expected to be an empty list for now. Later
slices add concrete step types; each step is expected to be a callable
that takes a block and returns the processed block, so the loop below is
already correct for non-empty chains without further changes.

`CompileChain` bridges a Voice's DECLARATIVE chain (`EffectStep` data --
see `voice_engine.voice`) to the compiled, callable form `ProcessChain`
expects. No concrete Effect Step types exist yet (pitch shift, ring
modulation, etc. arrive in later slices, 11 onward), so there is nothing
to dispatch on yet -- it only needs to correctly compile an empty chain
to an empty compiled list. The loop is kept in place so later slices can
add per-type compilation without restructuring this function.
"""
from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from voice_engine.voice import EffectStep

AudioBlock = NDArray[np.float32]
# The runtime, callable form of an Effect Step, distinct from the
# declarative Effect Step data (type + params) defined in the Voice Bank
# (see CONTEXT.md) — later slices bridge from one to the other.
CompiledEffectStep = Callable[[AudioBlock], AudioBlock]


def CompileChain(chain: list[EffectStep]) -> list[CompiledEffectStep]:
    """Compile a Voice's declarative Effect Step chain into the callable
    form `ProcessChain` expects.

    No concrete Effect Step types exist yet, so there is no per-type
    dispatch here -- only an empty `chain` is handled for now, which
    correctly compiles to an empty list of compiled steps. Later slices
    are expected to extend the loop body to compile each concrete
    Effect Step type as it's introduced.
    """
    compiledSteps: list[CompiledEffectStep] = []
    for step in chain:
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
