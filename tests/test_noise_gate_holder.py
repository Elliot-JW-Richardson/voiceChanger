"""Tests for the Noise Gate holder (Slice 26).

Verification (from SLICES.md, Slice 26):
- Given the Noise Gate holder is initialized
- When it is read before any change, and then set to a different level
  and read again
- Then the first read reports 0%, and the second read reports the
  newly set level
"""
from voice_engine.runtime import NoiseGateHolder


def test_NoiseGateHolderDefaultsTo0AndCanBeUpdated() -> None:
    noiseGateHolder = NoiseGateHolder()

    assert noiseGateHolder.Get() == 0

    noiseGateHolder.Set(40)

    assert noiseGateHolder.Get() == 40
