import sounddevice as sd
from flask import Flask, jsonify, send_from_directory, request
import librosa
import numpy as np

app = Flask(__name__)

SAMPLE_RATE = 48000
BLOCKSIZE = 1024
CHANNELS = 1

audio_stream = None  # global handle to the stream

current_pitch_semitones = 0.0

def audio_callback(indata, outdata, frames, time, status):
    if status:
        print("Status:", status)
    # Directly copy microphone input to speakers/headphones
    outdata[:] = indata


@app.route("/")
def index():
    # Serve the HTML page from the same directory
    return send_from_directory(".", "index.html")

@app.route("/update_pitch", methods=["POST"])
def update_pitch():

    global current_pitch_semitones

    data = request.get_json()

    if 'pitch' in data:
        print(data.get('pitch'))
        current_pitch_semitones = data.get('pitch')
    return jsonify({"status": "ok", "pitch": current_pitch_semitones})

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
        callback=audio_callback,
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
