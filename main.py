import sounddevice as sd

SAMPLE_RATE = 48000
BLOCKSIZE = 1024
CHANNELS = 1   # mono mic (you can use 2 for stereo devices)

def audio_callback(indata, outdata, frames, time, status):
    if status:
        print("Status:", status)
    outdata[:] = indata   # directly copy mic input → speakers

def main():
    print("Press Ctrl+C to stop.")
    with sd.Stream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCKSIZE,
        channels=CHANNELS,
        dtype="float32",
        callback=audio_callback
    ):
        sd.sleep(1000000000)  # keep running

if __name__ == "__main__":
    main()
