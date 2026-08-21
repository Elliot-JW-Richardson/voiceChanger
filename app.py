from pathlib import Path
from typing import Any, Optional

import sounddevice as sd
from flask import Flask, Response, jsonify, send_from_directory, request

from voice_engine.bank import LoadVoiceBank
from voice_engine.engine import ApplyMasterVolume, AudioBlock, CompiledChainCache, ProcessChain
from voice_engine.runtime import ActiveVoiceHolder, MasterVolumeHolder

app = Flask(__name__)

SAMPLE_RATE = 48000
# 8192 rather than the original 1024: pedalboard's PitchShift (Slice 11)
# has a large, roughly fixed per-call processing cost (~50ms, regardless
# of block size, since it's re-analyzed from scratch each call under
# reset=True -- see voice_engine/engine.py's CompilePitchShiftStep
# docstring) that overruns the ~21ms budget 1024 samples gives at 48kHz,
# causing real audible output underflow/input overflow. 8192 samples
# gives an ~170ms budget with a comfortable margin, at the cost of raising
# one-way audio latency to roughly that same ~170ms.
BLOCKSIZE = 8192
CHANNELS = 1

# Loaded relative to this file's own location (not the current working
# directory) so it works regardless of where the process is launched
# from -- same technique tests/test_passthrough_voice.py uses.
VOICES_DIRECTORY_PATH = Path(__file__).parent / "voices"
VOICE_BANK = LoadVoiceBank(str(VOICES_DIRECTORY_PATH))
ACTIVE_VOICE_HOLDER = ActiveVoiceHolder(VOICE_BANK)
MASTER_VOLUME_HOLDER = MasterVolumeHolder()
COMPILED_CHAIN_CACHE = CompiledChainCache(SAMPLE_RATE)

AUDIO_STREAM: Optional[sd.Stream] = None  # global handle to the stream


def AudioCallback(indata: AudioBlock, outdata: AudioBlock, frames: int, time: Any, status: sd.CallbackFlags) -> None:
    if status:
        print("Status:", status)
    # Route microphone input through the currently active Voice's chain
    # rather than copying it straight to speakers/headphones. Note: this
    # runs on sounddevice's own real-time audio thread, not the Flask
    # request thread (see CLAUDE.md's Architecture notes). Compiling the
    # chain fresh on every block was expensive enough to cause audible
    # underflow/overflow once pitch shift landed -- COMPILED_CHAIN_CACHE
    # only recompiles when the active Voice actually changes.
    activeVoice = ACTIVE_VOICE_HOLDER.Get()
    compiledChain = COMPILED_CHAIN_CACHE.Get(activeVoice)
    processedBlock = ProcessChain(compiledChain, indata)
    # Master Volume (see CONTEXT.md) is a single global gain applied
    # AFTER the Voice's Effect Step chain, independent of which Voice is
    # active -- not a Voice, not an Effect Step, so it's applied here
    # rather than folded into COMPILED_CHAIN_CACHE/ProcessChain above.
    masterVolumeLevel = MASTER_VOLUME_HOLDER.Get()
    outdata[:] = ApplyMasterVolume(processedBlock, masterVolumeLevel)


@app.route("/")
def Index() -> Response:
    # Serve the HTML page from the same directory
    return send_from_directory(".", "index.html")

@app.route("/voices", methods=["GET"])
def ListVoices() -> Response:
    voices = [{"id": voice.id, "name": voice.name} for voice in VOICE_BANK.voices]
    activeVoiceId = ACTIVE_VOICE_HOLDER.Get().id
    return jsonify({"voices": voices, "activeVoiceId": activeVoiceId})

@app.route("/voices/select", methods=["POST"])
def SelectVoice() -> Response:
    requestedId = request.get_json()["id"]
    selectedVoice = next(voice for voice in VOICE_BANK.voices if voice.id == requestedId)
    ACTIVE_VOICE_HOLDER.Set(selectedVoice)
    return jsonify({"status": "ok", "activeVoiceId": selectedVoice.id})

@app.route("/volume", methods=["GET"])
def GetVolume() -> Response:
    return jsonify({"level": MASTER_VOLUME_HOLDER.Get()})

@app.route("/start", methods=["POST"])
def StartStream() -> Response:
    global AUDIO_STREAM

    if AUDIO_STREAM is not None:
        return jsonify({"status": "already_running"})

    # If you want specific devices, set device=(input_index, output_index)
    # For now this uses default input + default output.
    AUDIO_STREAM = sd.Stream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCKSIZE,
        channels=CHANNELS,
        dtype="float32",
        callback=AudioCallback,
    )
    AUDIO_STREAM.start()
    return jsonify({"status": "started"})

@app.route("/stop", methods=["POST"])
def StopStream() -> Response:
    global AUDIO_STREAM

    if AUDIO_STREAM is None:
        return jsonify({"status": "not_running"})

    AUDIO_STREAM.stop()
    AUDIO_STREAM.close()
    AUDIO_STREAM = None
    return jsonify({"status": "stopped"})


@app.route("/status", methods=["GET"])
def Status() -> Response:
    running = AUDIO_STREAM is not None
    return jsonify({"running": running})


if __name__ == "__main__":
    # Important: disable Flask's reloader so the stream isn't started twice
    app.run(host="127.0.0.1", port=5000, debug=False)
