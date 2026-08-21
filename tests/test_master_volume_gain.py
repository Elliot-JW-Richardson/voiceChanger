"""Tests for Master Volume gain applied to a live audio block (Slice 14,
revised after ApplyMasterVolume switched from linear-gain-plus-hard-clip
to pedalboard Gain+Limiter -- see git history and this function's own
docstring for why: plain hard-clip gain left quiet real microphone input
still too quiet, since it has to stay conservative to avoid clipping the
loudest peaks).

Verification (from SLICES.md, Slice 14, still holds under the new
implementation):
- Given the Master Volume is set to a level that would push a loud
  block's samples beyond the valid [-1, 1] range
- When that block is processed
- Then the output is scaled by the volume level and clipped so no
  sample exceeds [-1, 1]

Tested directly at the engine level via `ApplyMasterVolume`, the same
way tests/test_engine.py tests `ProcessChain` directly rather than
through the Flask app -- this doesn't need Flask or `AudioCallback` at
all. Exact output values aren't asserted for the boosted case (the
Limiter's compressor curve is nonlinear, unlike the old plain
multiplication) -- instead this checks the properties the acceptance
criteria actually cares about: boosted, some samples are pushed toward
the ceiling, and nothing ever exceeds [-1, 1].
"""
import numpy as np

from voice_engine.engine import ApplyMasterVolume


def test_ApplyMasterVolumeScalesAndStaysWithinValidRange() -> None:
    # Block shape/dtype matches sounddevice's indata/outdata convention:
    # float32, (frames, channels) — see tests/test_engine.py. Samples
    # near +-0.9 combined with a 150% level would push toward/past +-1.0
    # without limiting.
    sampleRate = 16000
    block = np.array([[0.9], [-0.9], [0.5], [-0.5]], dtype=np.float32)

    result = ApplyMasterVolume(block, 150, sampleRate)

    assert result.dtype == np.float32
    assert result.shape == block.shape
    assert np.max(result) <= 1.0
    assert np.min(result) >= -1.0
    # Boosting should make the quieter (non-limited) samples louder, not
    # just clip the existing peaks.
    assert abs(result[2, 0]) > abs(block[2, 0])
    assert abs(result[3, 0]) > abs(block[3, 0])


def test_ApplyMasterVolumeAt100PercentIsExactPassthrough() -> None:
    # 100% (the default) must be a true no-op -- the Limiter's compressor
    # stage can otherwise soften a near-full-scale sample even at nominal
    # 0dB gain, which would break the Passthrough Voice's guarantee of
    # being a truly unmodified signal at default settings (see
    # tests/test_app.py and CONTEXT.md's Passthrough Voice entry).
    sampleRate = 16000
    block = np.array([[0.99], [-0.99], [0.5], [-0.5]], dtype=np.float32)

    result = ApplyMasterVolume(block, 100, sampleRate)

    np.testing.assert_array_equal(result, block)


def test_ApplyMasterVolumeAtZeroPercentIsSilence() -> None:
    sampleRate = 16000
    block = np.array([[0.9], [-0.9], [0.5], [-0.5]], dtype=np.float32)

    result = ApplyMasterVolume(block, 0, sampleRate)

    np.testing.assert_array_equal(result, np.zeros_like(block))
