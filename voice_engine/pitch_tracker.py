"""Pitch Tracker: estimates a block's dominant fundamental frequency via
autocorrelation.

This is the first stage of the Vocoder Effect Step (see CONTEXT.md's
"Vocoder Effect Step (v2, scoped -- see ADR 0004)" entry): a real
vocoder's carrier must track the input voice's own pitch in real time
rather than sit at a fixed frequency. ADR 0004
(docs/adr/0004-vocoder-over-tuned-ring-mod.md) found, via spectral
analysis of a reference track, a fundamental moving 42-58Hz across a
melodic phrase -- a fixed-frequency carrier (as `ring_mod`'s oscillator
is, see `voice_engine.engine.CompileRingModStep`) provably cannot
reproduce that. Pitch tracking is therefore a genuine prerequisite for
the vocoder, not throwaway scaffolding; Slice 33 will call `DetectPitch`
once per block to drive the vocoder's pitch-tracked sawtooth carrier.

ALGORITHM: autocorrelation (per Slice 32's acceptance criteria, which
names the method explicitly -- not FFT-peak-picking or another pitch
detection algorithm). A periodic signal correlates strongly with a
time-shifted copy of itself when the shift (lag) equals one full period;
`DetectPitch` computes the block's autocorrelation via `numpy.correlate`
(fully vectorized -- no per-sample Python loop, per CLAUDE.md's
Real-time performance notes), searches the lag range corresponding to a
plausible human-voice fundamental (roughly 50-500Hz, covering ADR 0004's
observed 42-58Hz reference range plus normal speech) for its strongest
peak, and converts that peak's lag back to a frequency via
`sampleRate / lagInSamples`.

SCOPE: this is a pure analysis function -- no Effect Step, no Voice
Bank/YAML wiring, no live-callback integration (that's Slice 33). It has
no dependency on `pedalboard`, Flask, or any other part of the app, kept
decoupled and directly testable in isolation (see
tests/test_pitch_tracker.py). Silence/no-clear-peak handling is
deliberately simple (a flat-signal short-circuit plus a relative-peak-
strength threshold) -- full voiced/unvoiced detection is explicitly
Slice 35's job, not this slice's.
"""
import numpy as np
from numpy.typing import NDArray

AudioBlock = NDArray[np.float32]

MIN_FUNDAMENTAL_HZ = 50.0
MAX_FUNDAMENTAL_HZ = 500.0
# A candidate peak must retain at least this fraction of the zero-lag
# autocorrelation (the signal's own energy) to be treated as a genuine
# periodicity rather than noise -- a simple threshold, not a full
# voiced/unvoiced classifier (see module docstring).
MIN_PEAK_STRENGTH_RATIO = 0.1


def DetectPitch(block: AudioBlock, sampleRate: int) -> float:
    """Estimate the dominant fundamental frequency (in Hz) of an audio
    block via autocorrelation.

    block: (frames, channels) float32, matching this project's AudioBlock
        convention (see voice_engine.engine.AudioBlock). Only the first
        channel is analyzed -- every Voice in this project is mono.
    sampleRate: the audio stream's sample rate in Hz, needed to convert
        the detected peak's lag (in samples) to a frequency in Hz.

    Returns the detected frequency in Hz, or 0.0 if the block is silent/
    flat or no sufficiently strong periodicity is found within the
    50-500Hz search range (see module docstring's SCOPE note -- this is
    a deliberately simple fallback, not full voiced/unvoiced detection).
    """
    mono = block[:, 0].astype(np.float64)
    mono = mono - np.mean(mono)
    frameCount = mono.shape[0]

    if np.max(np.abs(mono)) < 1e-6:
        return 0.0

    # Full autocorrelation via numpy.correlate, then keep only
    # non-negative lags (the second half of 'full' mode's output) --
    # negative lags are a mirror image and carry no extra information
    # for a real-valued signal.
    autocorrelation = np.correlate(mono, mono, mode="full")
    autocorrelation = autocorrelation[frameCount - 1:]
    zeroLagEnergy = autocorrelation[0]

    if zeroLagEnergy <= 0:
        return 0.0

    minLag = int(sampleRate / MAX_FUNDAMENTAL_HZ)
    maxLag = min(int(sampleRate / MIN_FUNDAMENTAL_HZ), frameCount - 1)

    if minLag >= maxLag:
        return 0.0

    searchRegion = autocorrelation[minLag:maxLag + 1]
    peakOffset = int(np.argmax(searchRegion))
    peakLag = minLag + peakOffset
    peakStrength = searchRegion[peakOffset]

    if peakStrength / zeroLagEnergy < MIN_PEAK_STRENGTH_RATIO:
        return 0.0

    return sampleRate / peakLag
