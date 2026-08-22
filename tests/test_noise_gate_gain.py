"""Tests for the Noise Gate applied to a live audio block (Slice 27).

Verification (from SLICES.md, Slice 27):
- Given the Noise Gate is set to a level that would attenuate a quiet,
  noise-like block
- When that block is processed
- Then the output is measurably attenuated compared to processing it
  with the gate fully open, while a louder, voice-like block above the
  threshold remains largely unaffected

Tested directly at the engine level via `ApplyNoiseGate`, the same way
tests/test_master_volume_gain.py tests `ApplyMasterVolume` directly
rather than through the Flask app/`AudioCallback` -- this is the
established pattern for a "level -> pedalboard effect" engine function
(Slice 14's real DSP-property test was against `ApplyMasterVolume`
directly, even though the slice's goal talked about the live audio
callback).

Amplitudes and level chosen from scratch experiments against
`pedalboard.NoiseGate` directly (see this slice's implementation notes):
at 80%, the mapped `threshold_db` reliably gates a ~0.01-amplitude
noise-like block down to near silence within a single ~139ms block
(matching app.py's BLOCKSIZE=3072 @ SAMPLE_RATE=22050) under
`reset=True`, while a 0.5-amplitude sine tone (voice-like, well above
the threshold) is left essentially untouched.
"""
import numpy as np

from voice_engine.engine import ApplyNoiseGate


def test_ApplyNoiseGateAttenuatesQuietBlockRelativeToGateOpen() -> None:
    # Block shape/dtype matches sounddevice's indata/outdata convention:
    # float32, (frames, channels) -- see tests/test_engine.py. Low
    # amplitude (~0.01) noise-like block, clearly below the threshold a
    # sensitivity level of 80% maps to.
    sampleRate = 22050
    numFrames = 3072
    rng = np.random.default_rng(0)
    quietBlock = (rng.uniform(-1.0, 1.0, size=(numFrames, 1)) * 0.01).astype(np.float32)

    gateOpenResult = ApplyNoiseGate(quietBlock, 0, sampleRate)
    gatedResult = ApplyNoiseGate(quietBlock, 80, sampleRate)

    assert gatedResult.dtype == np.float32
    assert gatedResult.shape == quietBlock.shape
    gateOpenRms = np.sqrt(np.mean(gateOpenResult.astype(np.float64) ** 2))
    gatedRms = np.sqrt(np.mean(gatedResult.astype(np.float64) ** 2))
    # Gate fully open (level 0) is an exact bypass, so gateOpenRms is
    # just the original block's RMS -- the gated result must be
    # measurably quieter, not just marginally different.
    assert gatedRms < gateOpenRms * 0.1


def test_ApplyNoiseGateLeavesLoudBlockLargelyUnaffected() -> None:
    # Louder, voice-like block (a sine tone at amplitude 0.5) clearly
    # above the same 80% level's threshold -- should pass through the
    # gate largely unaffected.
    sampleRate = 22050
    numFrames = 3072
    time = np.arange(numFrames) / sampleRate
    loudBlock = (0.5 * np.sin(2 * np.pi * 200 * time)).astype(np.float32).reshape(-1, 1)

    gateOpenResult = ApplyNoiseGate(loudBlock, 0, sampleRate)
    gatedResult = ApplyNoiseGate(loudBlock, 80, sampleRate)

    gateOpenRms = np.sqrt(np.mean(gateOpenResult.astype(np.float64) ** 2))
    gatedRms = np.sqrt(np.mean(gatedResult.astype(np.float64) ** 2))
    # Envelope-follower effect, not a brick-wall gate -- allow a
    # generous relative tolerance rather than exact equality.
    assert abs(gatedRms - gateOpenRms) <= 0.1 * gateOpenRms


def test_ApplyNoiseGateAtZeroPercentIsExactPassthrough() -> None:
    # 0% (the default, "gate fully open") must be a true no-op --
    # without this bypass, NoiseGate could still act on a near-silent
    # block even at a maximally permissive threshold, which would break
    # the Passthrough Voice's guarantee of being a truly unmodified
    # signal at default settings (see tests/test_app.py and CONTEXT.md's
    # Passthrough Voice entry).
    sampleRate = 22050
    block = np.array([[0.9], [-0.9], [0.5], [-0.5]], dtype=np.float32)

    result = ApplyNoiseGate(block, 0, sampleRate)

    np.testing.assert_array_equal(result, block)
