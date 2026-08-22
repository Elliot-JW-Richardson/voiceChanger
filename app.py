from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import sounddevice as sd
from flask import Flask, Response, jsonify, send_from_directory, request

from voice_engine.bank import LoadVoiceBank
from voice_engine.engine import ApplyMasterVolume, ApplyNoiseGate, AudioBlock, CompiledChainCache, ProcessChain
from voice_engine.recording import SaveRecordingWav
from voice_engine.runtime import ActiveVoiceHolder, MasterVolumeHolder, NoiseGateHolder, RecordingHolder

app = Flask(__name__)

# 22050 rather than 16000: 16kHz's 8kHz Nyquist ceiling was cutting real
# speech clarity (reported as "mumbly") -- consonant/sibilant content
# lives partly above 8kHz. 22050 raises that ceiling to 11025Hz, a
# meaningful clarity improvement, while still being cheaper to process
# than 44.1/48kHz (pedalboard's PitchShift cost scales with sample rate --
# see CompilePitchShiftStep's docstring).
#
# IMPORTANT: the 16000/1024 configuration this replaced was benchmarked
# against pitch shift ALONE (Slice 11, before ring modulation or bitcrush
# existed) and never re-validated against the full worst-case chain (the
# Magos Voice's pitch-shift + ring-mod + bitcrush, Slice 22) -- doing so
# later found real occasional budget overruns (~1.7% of calls in one
# 300-call test) that pitch-shift-alone benchmarking had missed entirely.
# When tuning these constants, always benchmark against the heaviest
# Voice actually shipped (voices/magos.yaml currently), not a single
# Effect Step in isolation.
SAMPLE_RATE = 22050
# 3072 gives a 139ms budget. Benchmarked against the full Magos chain
# specifically (not pitch shift alone): 0/300 calls over budget across two
# independent runs, p99 ~51ms, worst observed max ~112ms (~1.25x margin
# even at that worst case). This machine's benchmarks show real run-to-run
# jitter (a "safe" 16000/1024 config passed 0/200 in one run and failed
# 5/300 in another) -- picked for a comfortable margin against that
# variance, not just a clean-looking single run. Higher latency than the
# previous 64ms, lower than the original underflow/overflow fix's 170ms.
BLOCKSIZE = 3072
CHANNELS = 1

# Loaded relative to this file's own location (not the current working
# directory) so it works regardless of where the process is launched
# from -- same technique tests/test_passthrough_voice.py uses.
VOICES_DIRECTORY_PATH = Path(__file__).parent / "voices"
VOICE_BANK = LoadVoiceBank(str(VOICES_DIRECTORY_PATH))
ACTIVE_VOICE_HOLDER = ActiveVoiceHolder(VOICE_BANK)
MASTER_VOLUME_HOLDER = MasterVolumeHolder()
NOISE_GATE_HOLDER = NoiseGateHolder()
COMPILED_CHAIN_CACHE = CompiledChainCache(SAMPLE_RATE)

# Local-only, gitignored (like reference_audio/) -- these are the user's
# own A/B test recordings, not project source, and not something to
# commit. Created on import if it doesn't exist yet.
RECORDINGS_DIRECTORY_PATH = Path(__file__).parent / "recordings"
RECORDINGS_DIRECTORY_PATH.mkdir(exist_ok=True)
RECORDING_HOLDER = RecordingHolder()

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
    # Noise Gate (see CONTEXT.md) is a single global control applied to
    # the raw microphone input BEFORE the Voice's Effect Step chain runs
    # -- the mirror image of Master Volume below, which applies AFTER.
    # Not a Voice, not an Effect Step, so it's applied here rather than
    # folded into COMPILED_CHAIN_CACHE/ProcessChain.
    noiseGateLevel = NOISE_GATE_HOLDER.Get()
    gatedInput = ApplyNoiseGate(indata, noiseGateLevel, SAMPLE_RATE)
    activeVoice = ACTIVE_VOICE_HOLDER.Get()
    compiledChain = COMPILED_CHAIN_CACHE.Get(activeVoice)
    processedBlock = ProcessChain(compiledChain, gatedInput)
    # Master Volume (see CONTEXT.md) is a single global gain applied
    # AFTER the Voice's Effect Step chain, independent of which Voice is
    # active -- not a Voice, not an Effect Step, so it's applied here
    # rather than folded into COMPILED_CHAIN_CACHE/ProcessChain above.
    masterVolumeLevel = MASTER_VOLUME_HOLDER.Get()
    outdata[:] = ApplyMasterVolume(processedBlock, masterVolumeLevel, SAMPLE_RATE)
    # Buffers a copy of the exact audio just sent to the speaker, if a
    # recording is in progress (see RecordingHolder's docstring for why
    # this only ever appends to an in-memory buffer -- no disk I/O here,
    # that would risk the same underflow/overflow class of bug this
    # project's Real-time performance notes warn against elsewhere).
    RECORDING_HOLDER.AppendBlock(outdata)


@app.route("/")
def Index() -> Response:
    # Serve the HTML page from the same directory
    return send_from_directory(".", "index.html")

@app.route("/voices", methods=["GET"])
def ListVoices() -> Response:
    voices = [{"id": voice.id, "name": voice.name, "test": voice.test} for voice in VOICE_BANK.voices]
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

@app.route("/volume", methods=["POST"])
def SetVolume() -> Response:
    requestedLevel = request.get_json()["level"]
    # MasterVolumeHolder itself does no range validation (see its
    # docstring in voice_engine/runtime.py) -- clamping to the valid
    # 0-400% range (see CONTEXT.md's Master Volume entry) is this
    # route's job.
    clampedLevel = max(0, min(400, requestedLevel))
    MASTER_VOLUME_HOLDER.Set(clampedLevel)
    return jsonify({"status": "ok", "level": clampedLevel})

@app.route("/noise_gate", methods=["GET"])
def GetNoiseGate() -> Response:
    return jsonify({"level": NOISE_GATE_HOLDER.Get()})

@app.route("/noise_gate", methods=["POST"])
def SetNoiseGate() -> Response:
    requestedLevel = request.get_json()["level"]
    # NoiseGateHolder itself does no range validation (mirrors
    # MasterVolumeHolder's docstring in voice_engine/runtime.py) --
    # clamping to the valid 0-100% range (see CONTEXT.md's Noise Gate
    # entry) is this route's job.
    clampedLevel = max(0, min(100, requestedLevel))
    NOISE_GATE_HOLDER.Set(clampedLevel)
    return jsonify({"status": "ok", "level": clampedLevel})

@app.route("/recordings/start", methods=["POST"])
def StartRecording() -> Response:
    # Labeled with whichever Voice is active RIGHT NOW -- if the user
    # switches Voice mid-recording, the label still reflects whatever was
    # active at the moment recording started (documented workflow:
    # stop/restart recording when switching Voices, don't switch
    # mid-take).
    activeVoiceId = ACTIVE_VOICE_HOLDER.Get().id
    RECORDING_HOLDER.Start(activeVoiceId)
    return jsonify({"status": "ok", "voiceId": activeVoiceId})

@app.route("/recordings/stop", methods=["POST"])
def StopRecording() -> Response:
    wasActive, voiceLabel, blocks = RECORDING_HOLDER.Stop()
    if not wasActive:
        return jsonify({"status": "not_recording"})

    # Microsecond resolution -- second-only resolution let two rapid
    # start/stop cycles collide on the same filename and silently
    # overwrite each other (caught by tests/test_recordings_api.py).
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    filename = f"{voiceLabel}_{timestamp}.wav"
    filePath = RECORDINGS_DIRECTORY_PATH / filename
    SaveRecordingWav(blocks, SAMPLE_RATE, str(filePath))
    return jsonify({"status": "ok", "filename": filename})

@app.route("/recordings", methods=["GET"])
def ListRecordings() -> Response:
    recordingFiles = sorted(
        RECORDINGS_DIRECTORY_PATH.glob("*.wav"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,  # newest first -- matches the "don't get confused
        # with stale examples" workflow this was built for.
    )
    return jsonify({"recordings": [path.name for path in recordingFiles]})

@app.route("/recordings/<filename>", methods=["GET"])
def GetRecording(filename: str) -> Response:
    # send_from_directory sanitizes `filename` against path traversal.
    return send_from_directory(str(RECORDINGS_DIRECTORY_PATH), filename)

@app.route("/recordings/clear", methods=["POST"])
def ClearRecordings() -> Response:
    recordingFiles = list(RECORDINGS_DIRECTORY_PATH.glob("*.wav"))
    for path in recordingFiles:
        path.unlink()
    return jsonify({"status": "ok", "cleared": len(recordingFiles)})

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
