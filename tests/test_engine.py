"""Tests for the Effect Engine's chain processor (Slice 1).

Verification (from SLICES.md, Slice 1):
- Given a Voice's chain contains no Effect Steps
- When a block of audio is processed through it
- Then the output block is identical to the input block
"""
import numpy as np

from voice_engine.engine import process_chain


def test_empty_chain_returns_block_unchanged():
    # Block shape/dtype matches sounddevice's indata/outdata convention:
    # float32, (frames, channels) — see app.py's audio_callback.
    rng = np.random.default_rng(0)
    block = rng.uniform(-1.0, 1.0, size=(1024, 1)).astype(np.float32)
    original = block.copy()

    result = process_chain([], block)

    assert result.dtype == np.float32
    assert result.shape == block.shape
    np.testing.assert_array_equal(result, original)
