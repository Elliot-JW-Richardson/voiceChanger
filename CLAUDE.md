# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A real-time microphone pass-through/voice-changer experiment. A Flask server (`app.py`) opens a `sounddevice.Stream` that copies mic input straight to speaker output via an audio callback, and serves a single-page UI (`index.html`) with Start/Stop controls and a pitch slider. `main.py` is a standalone CLI version of the same passthrough loop (no Flask, no pitch control) — useful for testing audio I/O in isolation without the web layer.

Pitch shifting is not wired up yet: the slider posts a semitone value to `/update_pitch`, which is stored in the `current_pitch_semitones` global, but `audio_callback` in `app.py` ignores it and just copies `indata` to `outdata` unmodified. The commented-out `apply_pitch_shift` function (using `librosa.effects.pitch_shift`) is a non-realtime prototype for where that logic would plug in — it is not called from the audio callback, and applying it there as-is would need to operate on the callback's `indata`/`outdata` buffers directly, since `librosa.effects.pitch_shift` is too slow for a live per-block callback at typical block sizes.

## Environment

- Python 3.9 (venv at `venv/`, based on `C:\Python39`)
- Key dependencies (no `requirements.txt` yet — installed directly into `venv`): `flask`, `sounddevice`, `librosa`, `numpy`
- Windows-only paths/tooling assumed by the existing venv

## Running

```
venv\Scripts\activate
python app.py          # Flask server on http://127.0.0.1:5000
```

Flask's reloader is explicitly disabled (`debug=False`) in `app.py` — re-enabling it would start the audio stream twice on each code reload.

For a bare CLI passthrough test without the web server/UI:

```
python main.py
```

Tests use `pytest` (installed into `venv`, not in `requirements.txt` yet):

```
venv\Scripts\python.exe -m pytest
```

There is no linter or build step in this repo currently.

## Code style

Deliberate deviation from PEP 8, established starting with the Slice 1 implementation:

- **Variables**: `camelCase` (e.g. `activeVoice`, `sampleRate`)
- **Functions and classes**: `PascalCase` (e.g. `def ProcessChain(...)`, `class VoiceBank`)
- **Global (module-level) variables**: `SCREAMING_SNAKE_CASE` (e.g. `SAMPLE_RATE`, `ACTIVE_VOICE`)
- **Exception**: pytest test functions keep the `test_` lowercase-snake-case prefix pytest's default discovery requires (e.g. `def test_empty_chain_returns_block_unchanged():`) — this is a framework constraint, not a style choice.
- **Fully type hinted**: every function/method signature has argument and return type annotations (including `-> None` where nothing is returned, and on test functions). Local variables don't need annotations unless the assigned value's type isn't obvious. Not currently enforced by a linter/type checker — it's a stated convention, not a CI gate.

`app.py` and `main.py` predate this convention and still use standard Python snake_case; they'll be brought into compliance as upcoming slices touch them (the audio callback rewrite in Slice 6, the pitch-endpoint removal in Slice 9), not retrofitted wholesale.

## Architecture notes

- `audio_stream` in `app.py` is a single module-level global holding the active `sd.Stream`. `/start` and `/stop` create/tear it down; `/status` reports whether it's `None`. There's no locking — this assumes a single browser client and no concurrent start/stop requests.
- The audio callback runs on `sounddevice`'s own real-time audio thread, not the Flask request thread. Any future change to `audio_callback` that reads `current_pitch_semitones` must treat it as being read from a different thread than the one that writes it (`/update_pitch`).
- Sample rate is fixed at 48000 Hz, block size 1024, mono (1 channel) — set as module-level constants in both `app.py` and `main.py` and currently duplicated between them rather than shared.
- Input/output devices are left at system defaults (`sd.Stream` called without a `device=` argument); per-device selection is not implemented.
