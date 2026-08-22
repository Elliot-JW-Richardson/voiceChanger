"""Tests for RecordingHolder (voice_engine/runtime.py), added for the
Voice A/B testing workflow -- lets the frontend record the live audio
callback's actual output, labeled by whichever Voice was active at the
time (not tied to a SLICES.md slice).

Verification (informal, mirroring this module's docstring):
- Starting a recording marks it active and clears any previous buffer
- Appending a block while inactive is a no-op
- Appending while active buffers the block
- Stopping returns whether a recording was active, its voice label, and
  the buffered blocks, then resets to the inactive/empty state
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

    wasActive, voiceLabel, blocks = holder.Stop()
    assert wasActive is False
    assert voiceLabel is None
    assert blocks == []


def test_StartThenAppendThenStopReturnsBufferedBlocksAndLabel() -> None:
    holder = RecordingHolder()
    firstBlock = np.ones((10, 1), dtype=np.float32)
    secondBlock = np.full((10, 1), 2.0, dtype=np.float32)

    holder.Start("magos")
    assert holder.IsActive() is True

    holder.AppendBlock(firstBlock)
    holder.AppendBlock(secondBlock)

    wasActive, voiceLabel, blocks = holder.Stop()

    assert wasActive is True
    assert voiceLabel == "magos"
    assert len(blocks) == 2
    np.testing.assert_array_equal(blocks[0], firstBlock)
    np.testing.assert_array_equal(blocks[1], secondBlock)


def test_StopResetsToInactiveEmptyState() -> None:
    holder = RecordingHolder()
    holder.Start("deep")
    holder.AppendBlock(np.ones((10, 1), dtype=np.float32))

    holder.Stop()

    assert holder.IsActive() is False
    wasActive, voiceLabel, blocks = holder.Stop()
    assert wasActive is False
    assert voiceLabel is None
    assert blocks == []


def test_StartClearsAnyPreviouslyBufferedBlocks() -> None:
    holder = RecordingHolder()
    holder.Start("magos")
    holder.AppendBlock(np.ones((10, 1), dtype=np.float32))

    # Starting again (e.g. a fresh take without stopping first) discards
    # whatever was already buffered under the old label.
    holder.Start("deep")
    _, voiceLabel, blocks = holder.Stop()

    assert voiceLabel == "deep"
    assert blocks == []


def test_AppendedBlockIsCopiedNotAliased() -> None:
    # The real-time audio callback reuses/mutates its own outdata buffer
    # across calls -- the holder must copy each block, not keep a
    # reference to a buffer that gets overwritten before Stop() reads it.
    holder = RecordingHolder()
    block = np.ones((10, 1), dtype=np.float32)

    holder.Start("magos")
    holder.AppendBlock(block)
    block[:] = 99.0  # mutate the original after appending

    _, _, blocks = holder.Stop()

    assert not np.array_equal(blocks[0], block)
    np.testing.assert_array_equal(blocks[0], np.ones((10, 1), dtype=np.float32))
