"""Tests for the Master Volume holder (Slice 13).

Verification (from SLICES.md, Slice 13):
- Given the Master Volume holder is initialized
- When it is read before any change, and then set to a different level
  and read again
- Then the first read reports 100%, and the second read reports the
  newly set level
"""
from voice_engine.runtime import MasterVolumeHolder


def test_MasterVolumeHolderDefaultsTo100AndCanBeUpdated() -> None:
    masterVolumeHolder = MasterVolumeHolder()

    assert masterVolumeHolder.Get() == 100

    masterVolumeHolder.Set(150)

    assert masterVolumeHolder.Get() == 150
