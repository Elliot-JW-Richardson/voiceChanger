"""Tests for the pitch tracker (Slice 32).

Verification (from SLICES.md, Slice 32):
- Given a block containing a pure tone of a known frequency
- When the pitch tracker analyzes it
- Then it reports a detected frequency close to the known frequency

This is the first slice of Band 7 (Vocoder, see CONTEXT.md's "Vocoder
Effect Step" entry and docs/adr/0004-vocoder-over-tuned-ring-mod.md):
pitch tracking is a genuine prerequisite for the vocoder's pitch-tracked
sawtooth carrier (Slice 33), which in turn needs to follow the input
voice's fundamental as it moves -- ADR 0004 found a reference track's
fundamental moving 42-58Hz, tracking a melody, motivating a real
per-block pitch detector rather than a fixed carrier frequency.

Verified similarly to tests/test_pitch_shift_step.py's frequency-domain
check (a pure sine wave of a known frequency, checked against an
expected frequency with some tolerance), but here via AUTOCORRELATION
(the acceptance criteria's explicit method) rather than an FFT peak --
`DetectPitch` is the pure numpy building block Slice 33 will call, not
an Effect Step, so this test calls it directly with no `EffectStep`/
`CompileChain` involved.

Two known frequencies (100Hz and 300Hz) are tested, spanning the
50-500Hz plausible human-voice fundamental range this project's pitch
tracker searches, to guard against a hardcoded/lucky single-frequency
implementation. The block is sized at this project's live BLOCKSIZE=3072
@ SAMPLE_RATE=22050 (see CLAUDE.md's Real-time performance notes) --
long enough to contain several full periods of even the lower test tone,
which autocorrelation needs to find a clear peak. A prototype run of the
autocorrelation approach at this exact sample rate/block size (not
committed) confirmed detected frequencies within ~2Hz of the known tone,
so a 5Hz absolute tolerance here is comfortable, not hopeful -- discrete
lag steps mean autocorrelation can't return an exact frequency, only the
nearest achievable one.

A silent (all-zero) block is also checked to return 0.0 rather than
crash or report a bogus frequency -- full voiced/unvoiced detection is
explicitly Slice 35's job, not this slice's, so this is just a basic
"don't blow up on silence" sanity check, per this slice's own scope note.
"""
import numpy as np

from voice_engine.pitch_tracker import DetectPitch

SAMPLE_RATE = 22050
BLOCKSIZE = 3072


def test_DetectPitchFindsKnownFrequencyOfPureTone() -> None:
    for knownFrequency in (100.0, 300.0):
        time = np.arange(BLOCKSIZE, dtype=np.float32) / SAMPLE_RATE
        sineWave = np.sin(2 * np.pi * knownFrequency * time).astype(np.float32)
        block = sineWave.reshape(-1, 1)

        detectedFrequency = DetectPitch(block, SAMPLE_RATE)

        assert abs(detectedFrequency - knownFrequency) < 5.0


def test_DetectPitchReturnsZeroOnSilence() -> None:
    block = np.zeros((BLOCKSIZE, 1), dtype=np.float32)

    detectedFrequency = DetectPitch(block, SAMPLE_RATE)

    assert detectedFrequency == 0.0
