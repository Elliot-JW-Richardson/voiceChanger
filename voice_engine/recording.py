"""Recording: saves a completed recording's buffered audio blocks
(see voice_engine.runtime.RecordingHolder) to a 16-bit PCM WAV file.

Deliberately uses Python's stdlib `wave` module rather than adding a new
dependency (e.g. `soundfile`) -- writing a mono 16-bit PCM WAV is simple
enough that stdlib is sufficient, and this project keeps its dependency
list minimal (see requirements.txt/CLAUDE.md's Environment section).

This is glue/persistence code, not real-time DSP -- it runs on a Flask
request thread after a recording has already stopped (see
voice_engine.runtime.RecordingHolder's docstring for why the real-time
audio callback thread only ever buffers in memory, never touches disk).
"""
import wave

import numpy as np
from numpy.typing import NDArray

AudioBlock = NDArray[np.float32]


def SaveRecordingWav(blocks: list[AudioBlock], sampleRate: int, filePath: str) -> None:
    """Concatenate `blocks` (each a (frames, channels) float32 array, the
    same shape convention used throughout voice_engine.engine) into one
    mono 16-bit PCM WAV file at `filePath`.

    An empty `blocks` list writes a valid, zero-frame WAV file rather
    than raising -- a harmless edge case (e.g. recording started and
    immediately stopped with no audio stream running), not an error
    worth special-casing at the caller.

    float32 samples in [-1.0, 1.0] are scaled to the full int16 range
    and clipped defensively (a Voice's own chain should already keep
    output within [-1.0, 1.0] -- see CompileLimiterStep's docstring for
    the one case this project has already found where that's NOT
    automatic -- but clipping here costs nothing and avoids writing a
    corrupt/wrapped-around WAV file if it isn't).
    """
    if blocks:
        concatenated = np.concatenate(blocks, axis=0)[:, 0]
    else:
        concatenated = np.zeros(0, dtype=np.float32)

    clamped = np.clip(concatenated, -1.0, 1.0)
    pcmSamples = (clamped * 32767.0).astype(np.int16)

    with wave.open(filePath, "wb") as wavFile:
        wavFile.setnchannels(1)
        wavFile.setsampwidth(2)
        wavFile.setframerate(sampleRate)
        wavFile.writeframes(pcmSamples.tobytes())
