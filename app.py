from pathlib import Path
from typing import Any

import sounddevice as sd
from flask import Flask, jsonify, send_from_directory, request
import librosa
import numpy as np

from voice_engine.bank import LoadVoiceBank
from voice_engine.engine import AudioBlock, CompileChain, ProcessChain
from voice_engine.runtime import ActiveVoiceHolder

app = Flask(__name__)

SAMPLE_RATE = 48000
BLOCKSIZE = 1024
CHANNELS = 1

# Loaded relative to this file's own location (not the current working
# directory) so it works regardless of where the process is launched
# from -- same technique tests/test_passthrough_voice.py uses.
VOICES_DIRECTORY_PATH = Path(__file__).parent / "voices"
VOICE_BANK = LoadVoiceBank(str(VOICES_DIRECTORY_PATH))
ACTIVE_VOICE_HOLDER = ActiveVoiceHolder(VOICE_BANK)

audio_stream = None  # global handle to the stream

def AudioCallback(indata: AudioBlock, outdata: AudioBlock, frames: int, time: Any, status: sd.CallbackFlags) -> None:
    if status:
        print("Status:", status)
    # Route microphone input through the currently active Voice's chain
    # rather than copying it straight to speakers/headphones. Note: this
    # runs on sounddevice's own real-time audio thread, not the Flask
    # request thread (see CLAUDE.md's Architecture notes).
    activeVoice = ACTIVE_VOICE_HOLDER.Get()
    compiledChain = CompileChain(activeVoice.chain)
    outdata[:] = ProcessChain(compiledChain, indata)


@app.route("/")
def index():
    # Serve the HTML page from the same directory
    return send_from_directory(".", "index.html")

@app.route("/voices", methods=["GET"])
def ListVoices():
    voices = [{"id": voice.id, "name": voice.name} for voice in VOICE_BANK.voices]
    activeVoiceId = ACTIVE_VOICE_HOLDER.Get().id
    return jsonify({"voices": voices, "activeVoiceId": activeVoiceId})

@app.route("/voices/select", methods=["POST"])
def SelectVoice():
    requestedId = request.get_json()["id"]
    selectedVoice = next(voice for voice in VOICE_BANK.voices if voice.id == requestedId)
    ACTIVE_VOICE_HOLDER.Set(selectedVoice)
    return jsonify({"status": "ok", "activeVoiceId": selectedVoice.id})

@app.route("/start", methods=["POST"])
def start_stream():
    global audio_stream

    if audio_stream is not None:
        return jsonify({"status": "already_running"})

    # If you want specific devices, set device=(input_index, output_index)
    # For now this uses default input + default output.
    audio_stream = sd.Stream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCKSIZE,
        channels=CHANNELS,
        dtype="float32",
        callback=AudioCallback,
    )
    audio_stream.start()
    return jsonify({"status": "started"})

# def apply_pitch_shift(x, sr, semitones):
#     """
#     Pitch shift using librosa. This is NOT the most efficient for real-time,
#     but is okay for experimenting.
#
#     x: 1D numpy array
#     sr: sample rate
#     semitones: number of semitones to shift
#     """
#     if abs(semitones) < 1e-6:
#         return x
#     # librosa expects float32 / float64
#     y = librosa.effects.pitch_shift(x.astype(np.float32), sr=sr, n_steps=semitones)
#     # Ensure we return the same length as input; trim or pad as needed
#     if len(y) > len(x):
#         y = y[:len(x)]
#     elif len(y) < len(x):
#         y = np.pad(y, (0, len(x) - len(y)), mode="constant")
#     return y

@app.route("/stop", methods=["POST"])
def stop_stream():
    global audio_stream

    if audio_stream is None:
        return jsonify({"status": "not_running"})

    audio_stream.stop()
    audio_stream.close()
    audio_stream = None
    return jsonify({"status": "stopped"})


@app.route("/status", methods=["GET"])
def status():
    running = audio_stream is not None
    return jsonify({"running": running})


if __name__ == "__main__":
    # Important: disable Flask's reloader so the stream isn't started twice
    app.run(host="127.0.0.1", port=5000, debug=False)
