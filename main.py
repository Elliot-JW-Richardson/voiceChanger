from typing import Any

import numpy as np
import sounddevice as sd
from numpy.typing import NDArray

SAMPLE_RATE = 48000
BLOCKSIZE = 1024
CHANNELS = 1   # mono mic (you can use 2 for stereo devices)

AudioBlock = NDArray[np.float32]


def AudioCallback(indata: AudioBlock, outdata: AudioBlock, frames: int, time: Any, status: sd.CallbackFlags) -> None:
    if status:
        print("Status:", status)
    outdata[:] = indata   # directly copy mic input → speakers


def Main() -> None:
    print("Press Ctrl+C to stop.")
    with sd.Stream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCKSIZE,
        channels=CHANNELS,
        dtype="float32",
        callback=AudioCallback
    ):
        sd.sleep(1000000000)  # keep running

if __name__ == "__main__":
    Main()
