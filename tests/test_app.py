"""Tests for live audio routed through the active Voice (Slice 6).

Verification (from SLICES.md, Slice 6):
- Given the active Voice is Passthrough
- When a block of microphone audio is processed
- Then the output block equals the input block, produced via the
  active-Voice mechanism rather than a direct copy

Importing `app` loads the real `voices/` directory shipped with the
project into a module-level Voice Bank and Active Voice holder; the
active Voice defaults to Passthrough because `voices/passthrough.yaml`
is marked `default: true` (see tests/test_passthrough_voice.py), so this
test doesn't need to select a Voice explicitly to satisfy the "Given"
precondition.
"""
import numpy as np

from app import AudioCallback


def test_AudioCallbackPassesThroughWhenActiveVoiceIsPassthrough() -> None:
    # Block shape/dtype matches sounddevice's indata/outdata convention:
    # float32, (frames, channels) — see tests/test_engine.py.
    rng = np.random.default_rng(0)
    indata = rng.uniform(-1.0, 1.0, size=(1024, 1)).astype(np.float32)
    outdata = np.zeros_like(indata)

    AudioCallback(indata, outdata, 1024, None, None)

    np.testing.assert_array_equal(outdata, indata)
