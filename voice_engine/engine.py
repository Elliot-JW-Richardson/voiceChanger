"""Effect Engine: applies a Voice's ordered Effect Step chain to an audio block.

An Effect Step (see CONTEXT.md) is one entry in a DSP Voice's chain: an
effect type plus its parameters. A DSP Voice is an ordered list of Effect
Steps applied in sequence to each audio block.

`CompileChain` bridges a Voice's DECLARATIVE chain (`EffectStep` data --
see `voice_engine.voice`) to the compiled, callable form `ProcessChain`
expects. Slice 11 adds the first concrete Effect Step type, pitch shift
(via `pedalboard`), which needs the stream's sample rate to shift
correctly -- hence `CompileChain` takes `sampleRate` and bakes it into
the closures it builds for steps that need it. Slice 19 adds the second
concrete type, ring modulation (a trivial custom oscillator multiply --
`pedalboard` doesn't provide it). Slice 20 adds the third, distortion/
bitcrush (via `pedalboard.Bitcrush`). Slice 23 adds the fourth, EQ (via
`pedalboard.LowShelfFilter`/`HighShelfFilter`). Slice 24 adds the fifth
and final palette type, reverb (via `pedalboard.Reverb`), completing the
Effect palette (see CONTEXT.md). Slice 33 adds `vocoder`, a distinct
Effect Step type from the rest of the palette (see CONTEXT.md's "Vocoder
Effect Step (v2, scoped -- see ADR 0004)" entry) -- a pitch-tracked
sawtooth carrier, the first of several staged sub-slices (Band 7) toward
a full formant vocoder.

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
from pedalboard import Bitcrush, Gain, HighShelfFilter, Limiter, LowShelfFilter, NoiseGate, Pedalboard, PitchShift, Reverb

from voice_engine.pitch_tracker import DetectPitch
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
    criteria (see SLICES.md, Slice 11), unlike ring modulation's Slice 19,
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


def CompileRingModStep(step: EffectStep, sampleRate: int) -> CompiledEffectStep:
    """Compile a `ring_mod` Effect Step into a callable that multiplies a
    block by a sine oscillator (see CONTEXT.md's Effect palette entry:
    "multiplies the signal by a sine oscillator", a trivial custom DSP
    implementation -- unlike the rest of the palette, `pedalboard` doesn't
    provide ring modulation).

    Unlike `CompilePitchShiftStep` (stateless across calls -- each block
    is processed independently via `reset=True`), the oscillator here
    MUST carry its phase continuously across successive calls to the
    returned closure (Slice 19's acceptance criteria): the running time
    `phaseSeconds` is captured by the closure and advanced by
    `framesInBlock / sampleRate` on every call via `nonlocal`, so the next
    call's oscillator picks up exactly where the previous one left off
    instead of restarting at t=0.

    No clipping is needed -- multiplying a signal already in [-1.0, 1.0]
    by an oscillator also in [-1.0, 1.0] can't exceed [-1.0, 1.0].
    """
    frequency = step.params["frequency"]
    phaseSeconds = 0.0

    def RingModStep(block: AudioBlock) -> AudioBlock:
        nonlocal phaseSeconds
        framesInBlock = block.shape[0]
        time = phaseSeconds + np.arange(framesInBlock, dtype=np.float64) / sampleRate
        oscillator = np.sin(2 * np.pi * frequency * time).astype(np.float32)
        phaseSeconds += framesInBlock / sampleRate
        return block * oscillator.reshape(-1, 1)

    return RingModStep


def CompileBitcrushStep(step: EffectStep, sampleRate: int) -> CompiledEffectStep:
    """Compile a `bitcrush` Effect Step into a callable that runs a block
    through `pedalboard.Bitcrush` (see CONTEXT.md's Effect palette entry:
    "distortion/bitcrush (grit)").

    Follows the exact same pattern as `CompilePitchShiftStep`: the
    `Pedalboard`/`Bitcrush` instance is constructed ONCE here, at compile
    time, and reused for every subsequent block via the closure --
    constructing it per-block would be expensive setup work happening on
    the real-time audio callback thread, which is the bug class this
    project's "Real-time performance" notes (CLAUDE.md) warn against.

    `.process()` is called with the default `reset=True`, same rationale
    as pitch shift: it guarantees the output is always the SAME LENGTH as
    the input block, a hard requirement of this project's fixed-block-size
    `outdata[:] = ...` contract. Bitcrush is stateless across blocks (no
    phase or buffered samples to carry, unlike ring modulation), so this
    costs nothing here.

    `step.params["bit_depth"]` matches `pedalboard.Bitcrush`'s own
    constructor parameter name (`Bitcrush(bit_depth=8)` by default); each
    sample is quantized onto `2 ** bit_depth` values per pedalboard's own
    docs (though the true number of distinct sample values observed in
    output also depends on how those levels tile across the signal's
    actual [-1, 1] range -- see tests/test_bitcrush_step.py).
    """
    bitDepth = step.params["bit_depth"]
    pedalboardChain = Pedalboard([Bitcrush(bit_depth=bitDepth)])

    def BitcrushStep(block: AudioBlock) -> AudioBlock:
        crushedBlock = pedalboardChain.process(block, sampleRate, reset=True)
        return crushedBlock.astype(np.float32)

    return BitcrushStep


def CompileEqStep(step: EffectStep, sampleRate: int) -> CompiledEffectStep:
    """Compile an `eq` Effect Step into a callable that runs a block
    through `pedalboard.LowShelfFilter` or `pedalboard.HighShelfFilter`
    (see CONTEXT.md's Effect palette entry: "EQ (low/high shelf)").

    Follows the exact same pattern as `CompilePitchShiftStep`/
    `CompileBitcrushStep`: the `Pedalboard`/shelf-filter instance is
    constructed ONCE here, at compile time, and reused for every
    subsequent block via the closure -- constructing it per-block would
    be expensive setup work happening on the real-time audio callback
    thread, the bug class this project's "Real-time performance" notes
    (CLAUDE.md) warn against.

    `step.params["band"]` selects which shelf filter to build: `"low"`
    for `LowShelfFilter` (boosts/cuts frequencies BELOW its cutoff) or
    `"high"` for `HighShelfFilter` (boosts/cuts frequencies ABOVE its
    cutoff). `step.params["cutoff_frequency_hz"]` and
    `step.params["gain_db"]` map directly onto the matching pedalboard
    constructor parameters of the same names; `q` is left at pedalboard's
    own default (no Voice has needed to tune it yet).

    `.process()` is called with the default `reset=True`, same rationale
    as pitch shift and bitcrush: it guarantees the output is always the
    SAME LENGTH as the input block, a hard requirement of this project's
    fixed-block-size `outdata[:] = ...` contract. Like bitcrush, a shelf
    filter has no cross-block state this project's acceptance criteria
    care about, so this costs nothing here.
    """
    band = step.params["band"]
    cutoffFrequencyHz = step.params["cutoff_frequency_hz"]
    gainDb = step.params["gain_db"]

    if band == "low":
        shelfFilter = LowShelfFilter(cutoff_frequency_hz=cutoffFrequencyHz, gain_db=gainDb)
    elif band == "high":
        shelfFilter = HighShelfFilter(cutoff_frequency_hz=cutoffFrequencyHz, gain_db=gainDb)
    else:
        raise ValueError(f"Unknown EQ band: {band}")

    pedalboardChain = Pedalboard([shelfFilter])

    def EqStep(block: AudioBlock) -> AudioBlock:
        eqedBlock = pedalboardChain.process(block, sampleRate, reset=True)
        return eqedBlock.astype(np.float32)

    return EqStep


def CompileReverbStep(step: EffectStep, sampleRate: int) -> CompiledEffectStep:
    """Compile a `reverb` Effect Step into a callable that runs a block
    through `pedalboard.Reverb` (see CONTEXT.md's Effect palette entry:
    "reverb"), the fifth and final Effect palette type.

    Follows the exact same pattern as `CompilePitchShiftStep`/
    `CompileBitcrushStep`/`CompileEqStep`: the `Pedalboard`/`Reverb`
    instance is constructed ONCE here, at compile time, and reused for
    every subsequent block via the closure -- constructing it per-block
    would be expensive setup work happening on the real-time audio
    callback thread, the bug class this project's "Real-time
    performance" notes (CLAUDE.md) warn against.

    `step.params["wet_level"]` and `step.params["room_size"]` map
    directly onto `pedalboard.Reverb`'s constructor parameters of the
    same names (`wet_level` controls how much of the reverberated signal
    is mixed into the output; `room_size` controls decay length/
    character); `damping`, `dry_level`, `width`, and `freeze_mode` are
    left at pedalboard's own defaults (no Voice has needed to tune them
    yet).

    `.process()` is called with the default `reset=True`, same rationale
    as the other Effect Steps: it guarantees the output is always the
    SAME LENGTH as the input block, a hard requirement of this project's
    fixed-block-size `outdata[:] = ...` contract. Unlike bitcrush/EQ,
    reverb DOES have meaningful cross-block state (the decay tail) --
    `reset=True` means that tail is cut off/reset at each block boundary
    in the live callback rather than carrying into the next block, the
    same accepted limitation `CompilePitchShiftStep`'s docstring already
    documents for pitch shift (see CLAUDE.md's Real-time performance
    point 3). This is fine for this slice's acceptance criteria, which
    only requires a decay tail extending beyond the impulse's position
    WITHIN one `process()` call, not across the live callback's block
    boundaries.
    """
    wetLevel = step.params["wet_level"]
    roomSize = step.params["room_size"]
    pedalboardChain = Pedalboard([Reverb(wet_level=wetLevel, room_size=roomSize)])

    def ReverbStep(block: AudioBlock) -> AudioBlock:
        reverbedBlock = pedalboardChain.process(block, sampleRate, reset=True)
        return reverbedBlock.astype(np.float32)

    return ReverbStep


def CompileVocoderStep(step: EffectStep, sampleRate: int) -> CompiledEffectStep:
    """Compile a `vocoder` Effect Step into a callable that replaces a
    block's own waveform with a pitch-tracked sawtooth carrier (see
    CONTEXT.md's "Vocoder Effect Step (v2, scoped -- see ADR 0004)" entry
    and docs/adr/0004-vocoder-over-tuned-ring-mod.md).

    Unlike `CompileRingModStep`'s fixed-frequency oscillator, this
    carrier's frequency is re-derived every block from the block's OWN
    content: `DetectPitch` (voice_engine.pitch_tracker, Slice 32) runs
    once per call to find that block's detected fundamental, and the
    sawtooth is synthesized at exactly that frequency. This is what lets
    the carrier track a moving melody (ADR 0004's reference-track
    analysis found a fundamental moving 42-58Hz) rather than sit at one
    tuned frequency, which ADR 0004 found provably cannot reproduce a
    melody-tracking harmonic series.

    SAWTOOTH, NOT SINE: `phase = (frequency * t) % 1.0; sawtooth =
    2 * phase - 1.0` is a rising-ramp sawtooth. Its Fourier series
    contains energy at every harmonic of `frequency` (decaying as 1/n),
    unlike a sine's single spectral line -- this is what gives the
    output the "rich multi-harmonic structure" this slice's acceptance
    criteria (SLICES.md, Slice 33) asks for, and is a genuine step toward
    the reference track's observed dense harmonic series (ADR 0004).

    PHASE RESETS EVERY BLOCK (`t = np.arange(framesInBlock) / sampleRate`
    starts at 0 on every call, no `nonlocal` phase accumulator) -- this
    is a deliberate design choice, not an oversight, and is the OPPOSITE
    of `CompileRingModStep`'s continuous-phase carrier. Ring modulation's
    Slice 19 acceptance criteria specifically tested phase continuity
    across a block boundary; this slice's acceptance criteria does not --
    it only requires each block's OWN dominant frequency to match that
    block's OWN detected pitch, which a per-block-reset carrier already
    satisfies. It mirrors this project's established `reset=True`
    convention (see `CompilePitchShiftStep`'s docstring): each block is
    treated as its own complete, independent unit rather than carrying
    state across the block boundary. A future slice could add phase
    continuity if a later acceptance criteria needs it, the same way
    ring modulation's did.

    UNVOICED FALLBACK: if `DetectPitch` returns 0.0 (silence or no clear
    periodicity), this returns a silent (all-zero) block. Full voiced/
    unvoiced handling (a noise carrier instead of silence) is explicitly
    Slice 35's job, not this slice's -- see SLICES.md.

    AMPLITUDE: a fixed placeholder of 0.7 -- comfortably within
    [-1.0, 1.0] with headroom to spare, chosen simply as "clearly
    audible, no clipping risk," not a value with any deeper meaning. The
    block's own waveform is being REPLACED, not scaled, so there is no
    input amplitude to match yet; Slice 34 will shape amplitude (and much more
    -- the actual spectral envelope) from the input's own extracted
    formant envelope, per CONTEXT.md's Vocoder entry. Don't over-engineer
    amplitude matching here.

    No expensive one-time setup is needed (no `Pedalboard`/plugin
    instance to construct, unlike most of this file's other `Compile*Step`
    functions) -- like `CompileRingModStep`, the oscillator math is cheap
    enough to live entirely inside the returned closure.
    """
    carrierAmplitude = 0.7

    def VocoderStep(block: AudioBlock) -> AudioBlock:
        framesInBlock = block.shape[0]
        detectedFrequency = DetectPitch(block, sampleRate)

        if detectedFrequency <= 0.0:
            return np.zeros_like(block)

        time = np.arange(framesInBlock, dtype=np.float64) / sampleRate
        phase = (detectedFrequency * time) % 1.0
        sawtooth = (2.0 * phase - 1.0) * carrierAmplitude
        return sawtooth.reshape(-1, 1).astype(np.float32)

    return VocoderStep


def CompileChain(chain: list[EffectStep], sampleRate: int) -> list[CompiledEffectStep]:
    """Compile a Voice's declarative Effect Step chain into the callable
    form `ProcessChain` expects.

    sampleRate: the audio stream's sample rate in Hz, needed by Effect
        Step types (e.g. pitch shift) whose underlying DSP depends on it.

    Dispatches by each step's `type`; `pitch_shift` (Slice 11), `ring_mod`
    (Slice 19), `bitcrush` (Slice 20), `eq` (Slice 23), and `reverb`
    (Slice 24) are the concrete types handled so far -- the full Effect
    palette (see CONTEXT.md). `vocoder` (Slice 33) is a further, distinct
    Effect Step type layered on top of that palette (see CONTEXT.md's
    "Vocoder Effect Step (v2, scoped -- see ADR 0004)" entry), not one of
    the original five palette entries itself. Any other type raises
    `NotImplementedError`.
    """
    compiledSteps: list[CompiledEffectStep] = []
    for step in chain:
        if step.type == "pitch_shift":
            compiledSteps.append(CompilePitchShiftStep(step, sampleRate))
        elif step.type == "ring_mod":
            compiledSteps.append(CompileRingModStep(step, sampleRate))
        elif step.type == "bitcrush":
            compiledSteps.append(CompileBitcrushStep(step, sampleRate))
        elif step.type == "eq":
            compiledSteps.append(CompileEqStep(step, sampleRate))
        elif step.type == "reverb":
            compiledSteps.append(CompileReverbStep(step, sampleRate))
        elif step.type == "vocoder":
            compiledSteps.append(CompileVocoderStep(step, sampleRate))
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


def ApplyMasterVolume(block: AudioBlock, level: int, sampleRate: int) -> AudioBlock:
    """Scale a block of audio by the Master Volume level (see CONTEXT.md's
    Master Volume entry and ADR 0002) using `pedalboard.Gain` followed by
    `pedalboard.Limiter`, rather than plain linear gain with a hard clip.

    level: a percentage, 0-400 (100 = unity gain, unchanged output),
        as tracked by `voice_engine.runtime.MasterVolumeHolder`.

    Deliberately separate from the Effect Step chain machinery above --
    Master Volume is a single global control applied AFTER a Voice's
    Effect Step chain, independent of which Voice is active; it is not
    itself an Effect Step and has no entry in `CompileChain`'s dispatch.

    WHY A LIMITER INSTEAD OF np.clip: plain linear gain + hard clip was
    the original implementation, but on quiet real microphone input
    (compounded by real signal loss through pitch shift and ring
    modulation -- see git history) it left audio still too quiet, because
    hard-clip gain has to stay conservative to avoid clipping the loudest
    peaks, which under-uses the headroom available for everything quieter
    than those peaks. A limiter allows pushing much closer to full scale
    -- benchmarked noticeably louder (RMS ~0.24 vs ~0.14) at the same
    nominal boost on a quiet test signal -- because it compresses into
    peaks smoothly instead of leaving that headroom unused. `Limiter`
    still hard-clips at 0dB as its own final safety net, so the
    [-1.0, 1.0] guarantee this function has always made still holds.

    Constructing `Pedalboard([Gain, Limiter])` fresh on every call is
    fine here -- benchmarked at under 0.4ms, nothing like the expensive
    per-call setup `CompilePitchShiftStep`'s docstring warns against.
    `level` can change on any call (the user can drag the volume slider
    at any time), so there is no fixed instance to cache the way
    `CompiledChainCache` caches a compiled Voice chain.

    `level == 100` (the default) bypasses Gain/Limiter entirely and
    returns `block` unchanged -- without this, the Limiter's compressor
    stage can still soften a near-full-scale sample even at nominal 0dB
    gain, which would break the Passthrough Voice's guarantee of being a
    truly unmodified mic-to-speaker signal at default settings (see
    CONTEXT.md's Passthrough Voice entry and tests/test_app.py).
    """
    if level <= 0:
        return np.zeros_like(block)
    if level == 100:
        return block

    gainDb = 20.0 * np.log10(level / 100.0)
    board = Pedalboard([Gain(gain_db=gainDb), Limiter(threshold_db=-1.0, release_ms=100.0)])
    limitedBlock = board.process(block, sampleRate, reset=True)
    return limitedBlock.astype(np.float32)


def ApplyNoiseGate(block: AudioBlock, level: int, sampleRate: int) -> AudioBlock:
    """Attenuate a block of audio below a threshold using
    `pedalboard.NoiseGate` (see CONTEXT.md's Noise Gate entry), applied
    to the raw microphone input BEFORE a Voice's Effect Step chain runs
    -- the mirror image of `ApplyMasterVolume`, which applies gain AFTER
    the chain.

    level: a sensitivity percentage, 0-100 (0 = gate fully open, no
        gating), as tracked by `voice_engine.runtime.NoiseGateHolder`.

    Deliberately separate from the Effect Step chain machinery above --
    like Master Volume, the Noise Gate is a single global control
    independent of which Voice is active; it is not itself an Effect
    Step and has no entry in `CompileChain`'s dispatch.

    LEVEL -> THRESHOLD_DB MAPPING: there's no single obviously-correct
    formula the way Master Volume's `20*log10(level/100)` gain
    conversion is exact, since "sensitivity" has no natural dB unit of
    its own. `threshold_db` is linearly mapped across a -60dB (very
    permissive -- only near-silence gets gated) to -20dB (aggressive --
    gates a fair amount of quiet signal) range: `threshold_db = -60 +
    (level / 100) * 40`. Confirmed via scratch experiments (see this
    slice's test docstring) that this range reliably gates a
    ~0.01-amplitude noise-like block down to near silence at level=80,
    while leaving a ~0.5-amplitude voice-like tone essentially
    untouched. `ratio=10` (pedalboard's own default) is a firm but not
    brick-wall gate; `attack_ms=1.0` (short, so the gate reacts within a
    single ~139ms block at this project's SAMPLE_RATE=22050/
    BLOCKSIZE=3072 -- see the "reset=True" note below) and
    `release_ms=50.0` (short enough to recover quickly once level rises
    above threshold, matching the "voice through largely unaffected"
    acceptance criteria).

    `.process()` is called with the default `reset=True`, same rationale
    as every other Effect Step in this file: it guarantees the output is
    always the SAME LENGTH as the input block, a hard requirement of
    this project's fixed-block-size `outdata[:] = ...` contract. Like
    Master Volume, this means the gate's envelope follower does not
    carry state across block boundaries in the live callback -- the
    short attack/release times above are chosen specifically so the gate
    can still act meaningfully within ONE block despite that, the same
    limitation `CompilePitchShiftStep`/`CompileReverbStep` already
    document for their own effects.

    Constructing `Pedalboard([NoiseGate])` fresh on every call is fine
    here, following `ApplyMasterVolume`'s own documented precedent:
    `level` can change on any call (the user can drag the Noise Gate
    slider at any time), so there is no fixed instance to cache the way
    `CompiledChainCache` caches a compiled Voice chain.

    `level <= 0` (the default, "gate fully open") bypasses NoiseGate
    entirely and returns `block` unchanged -- without this, even a
    maximally permissive threshold could still act on a near-silent
    block, which would break the Passthrough Voice's guarantee of being
    a truly unmodified mic-to-speaker signal at default settings (see
    CONTEXT.md's Passthrough Voice entry and tests/test_app.py).
    """
    if level <= 0:
        return block

    thresholdDb = -60.0 + (level / 100.0) * 40.0
    board = Pedalboard([NoiseGate(threshold_db=thresholdDb, ratio=10, attack_ms=1.0, release_ms=50.0)])
    gatedBlock = board.process(block, sampleRate, reset=True)
    return gatedBlock.astype(np.float32)


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
