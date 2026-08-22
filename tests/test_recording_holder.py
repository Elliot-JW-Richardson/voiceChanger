"""Tests for RecordingHolder (voice_engine/runtime.py), added for the
Voice A/B testing workflow -- lets the frontend record the live audio
callback's actual output, labeled by whichever Voice was active at the
time, along with a settings snapshot (Master Volume, Noise Gate, the
Voice's full chain, etc.) so a recording can be correctly interpreted
later even if those settings or the Voice's chain change afterward (not
tied to a SLICES.md slice).

Verification (informal, mirroring this module's docstring):
- Starting a recording marks it active, stores its voice label and
  settings snapshot, and clears any previous buffer
- Appending a block while inactive is a no-op
- Appending while active buffers the block
- Stopping returns whether a recording was active, its voice label,
  settings snapshot, and the buffered blocks, then resets to the
  inactive/empty state
"""
import numpy as np

from voice_engine.runtime import RecordingHolder


def test_RecordingHolderStartsInactive() -> None:
    holder = RecordingHolder()

    assert holder.IsActive() is False


def test_AppendBlockWhileInactiveIsANoOp() -> None:
    holder = RecordingHolder()
    block = np.ones((10, 1), dtype=np.float32)

    holder.AppendBlock(block)

    wasActive, voiceLabel, settings, blocks = holder.Stop()
    assert wasActive is False
    assert voiceLabel is None
    assert settings == {}
    assert blocks == []


def test_StartThenAppendThenStopReturnsBufferedBlocksLabelAndSettings() -> None:
    holder = RecordingHolder()
    firstBlock = np.ones((10, 1), dtype=np.float32)
    secondBlock = np.full((10, 1), 2.0, dtype=np.float32)
    settingsSnapshot = {"masterVolume": 150, "noiseGate": 20}

    holder.Start("magos", settingsSnapshot)
    assert holder.IsActive() is True

    holder.AppendBlock(firstBlock)
    holder.AppendBlock(secondBlock)

    wasActive, voiceLabel, settings, blocks = holder.Stop()

    assert wasActive is True
    assert voiceLabel == "magos"
    assert settings == settingsSnapshot
    assert len(blocks) == 2
    np.testing.assert_array_equal(blocks[0], firstBlock)
    np.testing.assert_array_equal(blocks[1], secondBlock)


def test_StopResetsToInactiveEmptyState() -> None:
    holder = RecordingHolder()
    holder.Start("deep", {"masterVolume": 100})
    holder.AppendBlock(np.ones((10, 1), dtype=np.float32))

    holder.Stop()

    assert holder.IsActive() is False
    wasActive, voiceLabel, settings, blocks = holder.Stop()
    assert wasActive is False
    assert voiceLabel is None
    assert settings == {}
    assert blocks == []


def test_StartClearsAnyPreviouslyBufferedBlocksAndSettings() -> None:
    holder = RecordingHolder()
    holder.Start("magos", {"masterVolume": 100})
    holder.AppendBlock(np.ones((10, 1), dtype=np.float32))

    # Starting again (e.g. a fresh take without stopping first) discards
    # whatever was already buffered under the old label/settings.
    holder.Start("deep", {"masterVolume": 200})
    _, voiceLabel, settings, blocks = holder.Stop()

    assert voiceLabel == "deep"
    assert settings == {"masterVolume": 200}
    assert blocks == []


def test_AppendedBlockIsCopiedNotAliased() -> None:
    # The real-time audio callback reuses/mutates its own outdata buffer
    # across calls -- the holder must copy each block, not keep a
    # reference to a buffer that gets overwritten before Stop() reads it.
    holder = RecordingHolder()
    block = np.ones((10, 1), dtype=np.float32)

    holder.Start("magos", {})
    holder.AppendBlock(block)
    block[:] = 99.0  # mutate the original after appending

    _, _, _, blocks = holder.Stop()

    assert not np.array_equal(blocks[0], block)
    np.testing.assert_array_equal(blocks[0], np.ones((10, 1), dtype=np.float32))
