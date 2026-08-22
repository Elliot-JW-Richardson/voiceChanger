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
from pedalboard import Bitcrush, Gain, HighpassFilter, HighShelfFilter, Limiter, LowpassFilter, LowShelfFilter, NoiseGate, Pedalboard, PitchShift, Reverb

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


FILTER_BANK_LOW_HZ = 150.0
FILTER_BANK_HIGH_HZ = 4000.0
# 4 bands, not the 6-8 CONTEXT.md's Vocoder entry/this slice's own design
# notes suggest as an example -- deliberately narrowed from an initial
# 7-band prototype. See this function's docstring's BAND COUNT VS
# SELECTIVITY TRADE-OFF note for why: it's what let a genuinely selective
# (multi-stage) filter bank coexist with Slice 33's already-shipped
# harmonic-richness test.
FILTER_BANK_NUM_BANDS = 4
# Cascading multiple Highpass+Lowpass pairs per band, rather than just
# one, is what gives each band real selectivity -- see this function's
# docstring's FILTER BANK SELECTIVITY note.
FILTER_BANK_STAGES_PER_BAND = 2
# Envelopes/formants change slowly relative to the audio signal itself --
# a LOW cutoff smooths a rectified band signal into a genuine amplitude
# envelope rather than passing the rectified waveform's own ripple
# through. 20-50Hz is CONTEXT.md/this slice's suggested range; 30Hz is
# comfortably inside it.
ENVELOPE_FOLLOWER_CUTOFF_HZ = 30.0
# A fixed makeup gain applied after averaging across bands, compensating
# for the substantial passband attenuation `FILTER_BANK_STAGES_PER_BAND`
# cascaded filter stages introduce -- see this function's docstring's
# NORMALIZATION note for how this value was chosen.
FILTER_BANK_MAKEUP_GAIN = 15.0
# The unvoiced-branch noise carrier's amplitude (Slice 35) -- same order
# of magnitude as the voiced branch's sawtooth `carrierAmplitude` (0.7)
# so unvoiced output isn't wildly louder/quieter than voiced output; a
# placeholder subject to future by-ear tuning, not precisely tuned yet
# (see CompileVocoderStep's docstring's CARRIER, UNVOICED CASE note).
NOISE_CARRIER_AMPLITUDE = 0.7
# Constructed ONCE at module level (not per-block, not per-compile) and
# reused across every call -- cheap enough to call per-block, but a fixed
# per-block seed would make the "noise" identically repeat every block,
# which is not how a real noise carrier should behave. See
# CompileVocoderStep's docstring's CARRIER, UNVOICED CASE note.
VOCODER_NOISE_CARRIER_RNG = np.random.default_rng()


def CompileVocoderStep(step: EffectStep, sampleRate: int) -> CompiledEffectStep:
    """Compile a `vocoder` Effect Step into a callable that shapes a
    pitch-tracked sawtooth carrier with the input voice's own spectral/
    formant envelope -- the classic filter-bank talkbox/vocoder technique
    (see CONTEXT.md's "Vocoder Effect Step (v2, scoped -- see ADR 0004)"
    entry: "combines a carrier ... with the input voice's own modulator
    envelope ... extracted via a filter bank + envelope followers and
    imposed onto the carrier") and docs/adr/0004-vocoder-over-tuned-ring-
    mod.md, which found "a dense near-complete harmonic series through at
    least the 9th harmonic" in the reference track -- the reason the
    filter bank below spans several harmonics up into the low kHz range,
    not just the fundamental.

    CARRIER, VOICED CASE (unchanged from Slice 33): `DetectPitch` (Slice
    32) finds the block's own fundamental every call, and a pitch-tracked
    sawtooth is synthesized at that frequency with its phase reset each
    block (see the historical version of this docstring, preserved in git
    history, for the full reasoning -- SAWTOOTH-NOT-SINE and
    PHASE-RESETS-EVERY-BLOCK both still apply exactly as before; that
    part of this function's behavior is deliberately untouched by this
    slice).

    CARRIER, UNVOICED CASE (Slice 35): when `DetectPitch` reports `<= 0.0`
    (silence, or no periodicity strong enough to clear
    `pitch_tracker.MIN_PEAK_STRENGTH_RATIO` -- see that module's
    docstring), the block is treated as UNVOICED (consonant-like input,
    e.g. "s"/"f"/"sh", per this slice's goal) rather than voiced. No new
    pitch-detection logic is needed here: `DetectPitch`'s existing
    `<= 0.0` signal already IS the voiced/unvoiced decision, since its own
    `MIN_PEAK_STRENGTH_RATIO` threshold is what makes genuine noise-like
    input report 0.0 in the first place (verified directly against
    `DetectPitch` in a scratch prototype -- see
    tests/test_vocoder_step.py's `test_VocoderStepUsesNoiseCarrierForUnvoicedInputButSawtoothForPitchedInput`
    docstring). Instead of synthesizing a sawtooth, a WHITE NOISE carrier
    is drawn from `VOCODER_NOISE_CARRIER_RNG` (a single
    `np.random.default_rng()` constructed once at MODULE level, not
    per-block or per-compile -- reused across every call/compile so
    successive blocks get genuinely fresh noise rather than either an
    expensive per-block `Generator` construction or, worse, identical
    repeating "noise" from a fixed per-block seed) at
    `NOISE_CARRIER_AMPLITUDE` (0.7, matching the sawtooth's
    `carrierAmplitude` -- comparable order of magnitude so unvoiced output
    isn't wildly louder/quieter than voiced output; not precisely tuned by
    ear yet, a placeholder subject to future by-ear tuning like this
    file's other Effect Step parameters, e.g. see `voices/*.yaml`'s own
    comments for that convention). This was NOT the previous behavior --
    Slices 33/34 returned `np.zeros_like(block)` (silence) for unvoiced
    input; this slice replaces that with a genuine noise carrier that then
    goes through the SAME shaping below, per the standard vocoder design
    of swapping the excitation signal (pulse-train-like carrier for
    voiced, noise for unvoiced) while keeping the modulator-envelope
    imposition itself identical.

    FILTER BANK: at COMPILE TIME, `FILTER_BANK_NUM_BANDS` (4) frequency
    bands are chosen, log-spaced from `FILTER_BANK_LOW_HZ` (150Hz) to
    `FILTER_BANK_HIGH_HZ` (4000Hz) -- log spacing because formants and
    harmonic structure matter more logarithmically than linearly, and
    this range covers several harmonics of typical voiced speech, not
    just the fundamental, per ADR 0004's dense-harmonic-series finding.
    For EACH band, two `Pedalboard` instances are built ONCE here (never
    inside the closure -- see this file's module docstring and
    CLAUDE.md's Real-time performance notes): a bandpass filter
    (`HighpassFilter` chained with `LowpassFilter`, isolating that band)
    and an envelope-follower lowpass filter (`ENVELOPE_FOLLOWER_CUTOFF_HZ`
    cutoff, smoothing a rectified band signal into an amplitude
    envelope).

    FILTER BANK SELECTIVITY: a single `HighpassFilter`+`LowpassFilter`
    pair is a gentle, 2-pole-ish rolloff with a LOT of cross-band
    leakage -- prototyping found a single-stage band's peak in-band gain
    only ~1.7x its gain 2.5 octaves outside the band, nowhere near enough
    for one band's content to be reliably distinguishable from another's;
    with that little selectivity, prototyping found the two-input
    differentiation this slice's acceptance criteria needs actually comes
    out BACKWARDS (the input that emphasizes a LOWER harmonic ends up
    with LESS energy in that region than the other input, not more) --
    a distant band's strongly-energized, poorly-isolated carrier content
    bleeds across into other bands' frequency territory. Cascading
    `FILTER_BANK_STAGES_PER_BAND` (2) Highpass+Lowpass pairs per band
    fixes the direction and gives clear, correctly-signed separation
    (see tests/test_vocoder_step.py's
    `test_VocoderStepShapesCarrierWithEachInputsOwnFormantEnvelope`
    docstring for the exact ratios prototyping found). This roughly
    doubles the filter bank's per-block cost, but that cost is tiny in
    absolute terms (benchmarked well under a few ms for the full 4-band
    bank at this project's SAMPLE_RATE=22050/BLOCKSIZE=3072, against a
    139ms budget) -- nowhere near pathological.

    BAND COUNT VS SELECTIVITY TRADE-OFF: an earlier prototype used 7
    (log-spaced, matching CONTEXT.md's "6-8" suggestion) narrow bands
    with 3 cascaded stages each for even sharper selectivity -- but that
    combination, while giving excellent two-input differentiation, also
    suppressed a PURE, single-frequency sine's synthesized-carrier
    harmonics almost entirely (each higher harmonic lives in its own
    narrow band, and a pure sine has essentially no energy outside its
    own fundamental's band, so that harmonic's envelope collapses to
    near-zero). That broke Slice 33's already-shipped
    `test_VocoderStepOutputHasRichHarmonicStructureUnlikeInputSine`,
    which deliberately uses a pure sine and expects the carrier's 2nd
    harmonic to survive strongly. Prototyping across band counts (2-8)
    and stage counts (1-3) found no combination that maximizes BOTH
    properties at once -- narrower/more-selective bands help
    differentiation but hurt pure-tone harmonic survival, and vice versa.
    4 wider bands with 2 cascaded stages was the best balance found: each
    band is wide enough that a pure sine's fundamental and its immediate
    neighboring harmonics mostly share a band (preserving that band's
    strong envelope and hence the carrier's own harmonics within it),
    while still being narrow/selective enough to separate the two test
    signals' differently-placed emphasized harmonics (the 3rd and 9th)
    into different bands. This is a real, deliberate trade-off, not an
    oversight -- a genuine per-harmonic-band vocoder (as an idealized
    design might use many more, narrower bands) would sound more
    articulate on real speech, at the cost of exactly this kind of
    pure-tone edge case. Revisiting band count/selectivity once this
    Effect Step is validated against real voice input (rather than
    synthetic test tones) is a reasonable future refinement, not required
    by this slice's acceptance criteria.

    PER-BLOCK SHAPING (in the closure, given the input block as the
    "modulator"): for each band, (a) the band's bandpass filter runs on
    the MODULATOR to isolate that band's content, (b) that's rectified
    (`np.abs`) and run through the band's envelope-follower lowpass
    filter to get a smoothed amplitude envelope, (c) the SAME band's
    bandpass filter runs on the CARRIER (sawtooth if voiced, white noise
    if unvoiced -- see CARRIER, UNVOICED CASE above) to isolate that
    band's content from the carrier, (d) the band-filtered carrier is
    multiplied by the band's envelope, and (e) that shaped band is summed
    into the output. This loop is UNCHANGED and UNIFIED across both
    voiced and unvoiced input (Slice 35): only the carrier waveform fed
    into it differs by branch, per the standard vocoder design of
    imposing the modulator's envelope onto whichever excitation signal is
    appropriate -- there is no separate unvoiced code path here, and
    unvoiced output is deliberately never left as silence or as a raw,
    unshaped noise burst.

    NORMALIZATION: after summing all bands, the result is divided by
    `FILTER_BANK_NUM_BANDS` (averaging, so summing more bands doesn't
    blow up the output just because there are more of them), then
    multiplied by `FILTER_BANK_MAKEUP_GAIN` (15.0) -- a fixed compensating
    gain. The makeup gain is needed because cascaded bandpass filtering
    is lossy: prototyping found the averaged-but-unboosted output was
    extremely quiet (well under a tenth of Slice 33's flat 0.7-amplitude
    carrier), because the very selectivity this slice depends on
    (FILTER BANK SELECTIVITY above) also throws away most of a
    narrowband signal's energy relative to a full-band one.
    `FILTER_BANK_MAKEUP_GAIN`'s exact value was chosen empirically via
    prototyping to comfortably clear Slice 33's rich-harmonic-structure
    threshold (found to land the output/input energy ratio at that
    test's 2nd harmonic around ~15x -- well past that test's >10x
    threshold) while keeping peak output amplitude well inside
    [-1.0, 1.0] (prototyping found peaks around ~0.4 on the test signals
    used here, comfortable headroom, no clipping risk) -- not a value
    with any deeper meaning beyond "satisfies both constraints with
    margin." Real loudness/level tuning against an actual live Voice is
    explicitly this file's Real-time performance point 5's job
    (CLAUDE.md), deferred to Slice 36 when this Effect Step is first
    wired into a real Voice, not this slice's.

    STATELESS-SAFE REUSE: each band's `Pedalboard` instance is called
    TWICE per closure call (once on the modulator, once on the carrier) --
    safe because `.process()` is called with `reset=True` throughout (see
    below), so there is no cross-call state for one call to corrupt for
    the other.

    `.process()` calls all use the default `reset=True`, the same
    rationale as every other `Compile*Step` in this file: it guarantees
    the output is always the SAME LENGTH as the input, a hard requirement
    of this project's fixed-block-size `outdata[:] = ...` contract. Like
    `CompilePitchShiftStep`/`CompileReverbStep`, this means no filter
    state (bandpass or envelope-follower) carries across the live
    callback's block boundaries -- an accepted limitation already
    documented for every other `pedalboard`-based Effect Step here.

    REAL-TIME BENCHMARKING NOTE: this function is only benchmarked in
    isolation so far (see FILTER BANK SELECTIVITY above), not yet against
    the full worst-case chain this project ships (CLAUDE.md's Real-time
    performance point 5) -- this slice doesn't wire `vocoder` into a live
    Voice yet (that's Slice 36), so that benchmarking is deferred to when
    it does.
    """
    carrierAmplitude = 0.7

    bandEdgesHz = np.logspace(np.log10(FILTER_BANK_LOW_HZ), np.log10(FILTER_BANK_HIGH_HZ), FILTER_BANK_NUM_BANDS + 1)
    bandpassFilters: list[Pedalboard] = []
    envelopeFollowers: list[Pedalboard] = []
    for bandIndex in range(FILTER_BANK_NUM_BANDS):
        bandLowHz = float(bandEdgesHz[bandIndex])
        bandHighHz = float(bandEdgesHz[bandIndex + 1])
        bandpassPlugins = []
        for _ in range(FILTER_BANK_STAGES_PER_BAND):
            bandpassPlugins.append(HighpassFilter(cutoff_frequency_hz=bandLowHz))
            bandpassPlugins.append(LowpassFilter(cutoff_frequency_hz=bandHighHz))
        bandpassFilters.append(Pedalboard(bandpassPlugins))
        envelopeFollowers.append(Pedalboard([LowpassFilter(cutoff_frequency_hz=ENVELOPE_FOLLOWER_CUTOFF_HZ)]))

    def VocoderStep(block: AudioBlock) -> AudioBlock:
        framesInBlock = block.shape[0]
        detectedFrequency = DetectPitch(block, sampleRate)

        if detectedFrequency <= 0.0:
            # Unvoiced (Slice 35): no clear pitch, so use a white-noise
            # carrier instead of a spuriously-pitched sawtooth.
            carrier = (VOCODER_NOISE_CARRIER_RNG.uniform(-1.0, 1.0, size=(framesInBlock, 1)) * NOISE_CARRIER_AMPLITUDE).astype(np.float32)
        else:
            time = np.arange(framesInBlock, dtype=np.float64) / sampleRate
            phase = (detectedFrequency * time) % 1.0
            sawtooth = (2.0 * phase - 1.0) * carrierAmplitude
            carrier = sawtooth.reshape(-1, 1).astype(np.float32)

        shapedOutput = np.zeros((framesInBlock, 1), dtype=np.float64)
        for bandpassFilter, envelopeFollower in zip(bandpassFilters, envelopeFollowers):
            modulatorBand = bandpassFilter.process(block, sampleRate, reset=True)
            rectifiedModulatorBand = np.abs(modulatorBand).astype(np.float32)
            bandEnvelope = envelopeFollower.process(rectifiedModulatorBand, sampleRate, reset=True)
            carrierBand = bandpassFilter.process(carrier, sampleRate, reset=True)
            shapedOutput += carrierBand.astype(np.float64) * bandEnvelope.astype(np.float64)

        shapedOutput = shapedOutput / FILTER_BANK_NUM_BANDS * FILTER_BANK_MAKEUP_GAIN
        return shapedOutput.astype(np.float32)

    return VocoderStep


SAWTOOTH_BLEND_CARRIER_AMPLITUDE = 0.7


def CompileSawtoothBlendStep(step: EffectStep, sampleRate: int) -> CompiledEffectStep:
    """Compile a `sawtooth_blend` Effect Step: MIX a pitch-tracked sawtooth
    carrier INTO the voice, rather than replacing the voice with one (see
    `CompileVocoderStep` above).

    WHY THIS EXISTS: real-hardware testing of `vocoder` found it destroyed
    intelligibility -- it discards the input block's actual waveform
    entirely and resynthesizes from only a detected pitch plus a handful
    of coarse per-band loudness envelopes, none of which carry the actual
    harmonic/formant detail a real voice needs to stay recognizable. This
    step takes the opposite approach: the ORIGINAL block passes through
    untouched, and a pitch-tracked sawtooth (the "electronic" texture the
    vocoder was also trying to add) is blended in on top at a tunable
    level, so the underlying voice's own clarity is never at risk -- at
    `mix=0.0` this is an exact passthrough, unlike `vocoder`, which has no
    such graceful floor.

    `step.params["mix"]`: 0.0-1.0, the fraction of the output that's
    sawtooth carrier vs. original voice (`output = (1-mix)*voice +
    mix*carrier`); no range validation here (consistent with every other
    per-Voice declarative param in this file, e.g. `pitch_shift`'s
    `semitones`, `eq`'s `gain_db` -- trusted to be set correctly in the
    Voice's YAML, not runtime-clamped).

    PITCH TRACKING: reuses `DetectPitch` exactly as `CompileVocoderStep`
    does (autocorrelation, 50-500Hz search range, per-block, no state
    carried across blocks). UNVOICED FALLBACK differs deliberately from
    `vocoder`'s Slice-35 noise-carrier design: when `DetectPitch` reports
    no clear pitch (silence, or a consonant with no clean periodicity),
    this step just passes the ORIGINAL block through unchanged for that
    block (mix effectively drops to 0), rather than mixing in white noise.
    This keeps the step's only moving part being the sawtooth carrier
    itself -- simpler, and avoids reintroducing noise-carrier behavior
    that hasn't been validated against real speech either. Worth
    revisiting once the sawtooth-blend mix level itself is validated by
    ear.

    CARRIER: an unshaped sawtooth at the detected frequency (phase resets
    every block, same formula/trade-off as `CompileVocoderStep`'s carrier
    -- see that function's docstring for the accepted-limitation
    reasoning), scaled by a fixed `SAWTOOTH_BLEND_CARRIER_AMPLITUDE`
    (0.7, matching `vocoder`'s own carrier amplitude placeholder) before
    the mix -- NOT shaped by any per-band envelope/filter bank, since the
    whole point here is to avoid the filter-bank/formant machinery that
    real-hardware testing found broke intelligibility. Re-tune
    `SAWTOOTH_BLEND_CARRIER_AMPLITUDE` and `mix` together by ear once this
    is validated on real hardware, same as any other Voice parameter (see
    CONTEXT.md's Voice Bank entry).
    """
    mix = step.params["mix"]

    def SawtoothBlendStep(block: AudioBlock) -> AudioBlock:
        framesInBlock = block.shape[0]
        detectedFrequency = DetectPitch(block, sampleRate)

        if detectedFrequency <= 0.0:
            return block

        time = np.arange(framesInBlock, dtype=np.float64) / sampleRate
        phase = (detectedFrequency * time) % 1.0
        sawtooth = (2.0 * phase - 1.0) * SAWTOOTH_BLEND_CARRIER_AMPLITUDE
        carrier = sawtooth.reshape(-1, 1).astype(np.float32)

        blended = (1.0 - mix) * block + mix * carrier
        return blended.astype(np.float32)

    return SawtoothBlendStep


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
    the original five palette entries itself. `sawtooth_blend` (added
    after real-hardware testing found `vocoder` destroyed intelligibility
    -- see `CompileSawtoothBlendStep`'s docstring) is a simpler
    alternative: it MIXES a pitch-tracked sawtooth into the voice instead
    of replacing the voice with one. Any other type raises
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
        elif step.type == "sawtooth_blend":
            compiledSteps.append(CompileSawtoothBlendStep(step, sampleRate))
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
