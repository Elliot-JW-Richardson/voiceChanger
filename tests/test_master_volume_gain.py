"""Tests for Master Volume gain applied to a live audio block (Slice 14).

Verification (from SLICES.md, Slice 14):
- Given the Master Volume is set to a level that would push a loud
  block's samples beyond the valid [-1, 1] range
- When that block is processed
- Then the output is scaled by the volume level and clipped so no
  sample exceeds [-1, 1]

Tested directly at the engine level via `ApplyMasterVolume`, the same
way tests/test_engine.py tests `ProcessChain` directly rather than
through the Flask app -- this doesn't need Flask or `AudioCallback` at
all.
"""
import numpy as np

from voice_engine.engine import ApplyMasterVolume


def test_ApplyMasterVolumeScalesAndClipsToValidRange() -> None:
    # Block shape/dtype matches sounddevice's indata/outdata convention:
    # float32, (frames, channels) — see tests/test_engine.py. Samples
    # near +-0.9 combined with a 150% level would scale to +-1.35,
    # outside the valid [-1, 1] range without clipping.
    block = np.array([[0.9], [-0.9], [0.5], [-0.5]], dtype=np.float32)

    result = ApplyMasterVolume(block, 150)

    assert result.dtype == np.float32
    assert result.shape == block.shape
    expected = np.array([[1.0], [-1.0], [0.75], [-0.75]], dtype=np.float32)
    np.testing.assert_allclose(result, expected, atol=1e-6)
    assert np.max(result) <= 1.0
    assert np.min(result) >= -1.0
