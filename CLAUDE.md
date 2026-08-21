# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A real-time microphone pass-through/voice-changer, being rebuilt slice by slice (see SLICES.md) into a DSP voice changer with a switchable, data-driven Voice Bank (see CONTEXT.md and ADR 0001). A Flask server (`app.py`) opens a `sounddevice.Stream` and routes mic input through the currently active Voice's effect chain via `AudioCallback`, and serves a single-page UI (`index.html`) with Start/Stop controls and a list of selectable Voices (`GET /voices`, `POST /voices/select`). `main.py` is a standalone CLI version of the original raw passthrough loop (no Flask, no Voice selection) — useful for testing audio I/O in isolation without the web layer; it has not been updated to route through the Voice Bank.

The old pitch slider and its `/update_pitch` endpoint have been retired entirely (Slices 8–9) in favor of Voice selection. As of the latest completed slice, the only shipped Voice is Passthrough (empty effect chain, functionally identical to the old raw copy) — real DSP effects (pitch shift, ring modulation, distortion, EQ, reverb) and additional character Voices land in later slices (11 onward, see SLICES.md). The original `apply_pitch_shift` prototype (using `librosa.effects.pitch_shift`) has been removed entirely — it was never wired into anything, and `librosa` is no longer a dependency; a real pitch-shift Effect Step will use `pedalboard` instead (see CONTEXT.md's Effect palette entry).

## Environment

- Python 3.9 (venv at `venv/`, based on `C:\Python39`)
- Dependencies pinned in `requirements.txt`: `flask`, `sounddevice`, `numpy`, `pyyaml`, `pytest`
- Windows-only paths/tooling assumed by the existing venv
- See [README.md](README.md) for setup/run instructions aimed at a human running this project (this file is aimed at Claude Code specifically)

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

Tests use `pytest`:

```
venv\Scripts\python.exe -m pytest
```

There is no linter or build step in this repo currently.

## Code style

Deliberate deviation from PEP 8, established starting with the Slice 1 implementation:

- **Variables**: `camelCase` (e.g. `activeVoice`, `sampleRate`)
- **Functions and classes**: `PascalCase` (e.g. `def ProcessChain(...)`, `class VoiceBank`)
- **Global (module-level) variables**: `SCREAMING_SNAKE_CASE` (e.g. `SAMPLE_RATE`, `ACTIVE_VOICE`)
- **Exception**: pytest test functions keep the mandatory lowercase `test_` prefix pytest's default discovery requires, but everything after it follows the normal PascalCase function rule (e.g. `def test_EmptyChainReturnsBlockUnchanged():`, not `test_empty_chain_returns_block_unchanged`). Only the literal `test_` is a framework constraint — the rest is not exempt from the convention.
- **Fully type hinted**: every function/method signature has argument and return type annotations (including `-> None` where nothing is returned, and on test functions). Local variables don't need annotations unless the assigned value's type isn't obvious. Not currently enforced by a linter/type checker — it's a stated convention, not a CI gate.

`app.py` and `main.py` originally predated this convention (snake_case, no type hints) but have since been brought fully into compliance, independent of the slice-by-slice Voice Bank work — including `main.py`, which still deliberately does a raw pass-through and is not routed through the Voice Bank (see Project overview above).

## Architecture notes

- `AUDIO_STREAM` in `app.py` is a single module-level global holding the active `sd.Stream`. `/start` and `/stop` create/tear it down; `/status` reports whether it's `None`. There's no locking — this assumes a single browser client and no concurrent start/stop requests.
- `VOICE_BANK` (a `VoiceBank`) is loaded once from the real `voices/` directory at module import time and never mutated afterward — safe to read from any thread. `ACTIVE_VOICE_HOLDER` (an `ActiveVoiceHolder`, see `voice_engine/runtime.py`) tracks which Voice is currently active and IS mutated across threads: `AudioCallback` reads it on sounddevice's own real-time audio thread, while `POST /voices/select` writes it on a Flask request thread. It's lock-guarded internally, so this is safe — unlike the old, now-removed `current_pitch_semitones` global, which had this same cross-thread hazard without a lock.
- Sample rate and block size are set as module-level constants in both `app.py` and `main.py`, currently duplicated between them rather than shared, and **differ between the two on purpose**: `app.py` uses 16000 Hz / 1024 (see the "Real-time performance" note below); `main.py` (no DSP, just a raw pass-through) stays at 48000 Hz / 1024 — it doesn't need the lower sample rate's processing headroom, and 48kHz is the more useful setting for a general "does my audio hardware work" sanity check. Both are mono (1 channel).
- Input/output devices are left at system defaults (`sd.Stream` called without a `device=` argument); per-device selection is not implemented.

### Real-time performance (read before adding a new Effect Step type)

`AudioCallback` runs once per audio block on sounddevice's real-time thread and must complete within `BLOCKSIZE / SAMPLE_RATE` seconds or the stream audibly glitches (`Status: output underflow` / `input overflow` printed to the console, heard as static). Two real bugs already hit this, both fixed in the same pass (not a planned slice — see git history around the Slice 12 follow-up commits):

1. **Don't recompile the chain every block.** `CompileChain` can be expensive per Effect Step (see #2). `AudioCallback` must go through `COMPILED_CHAIN_CACHE` (`CompiledChainCache` in `voice_engine/engine.py`), which only recompiles when the active Voice's id actually changes, not on every block.
2. **Don't do expensive per-step setup inside the compiled closure.** A `Compile<X>Step` function's expensive part (e.g. constructing a `pedalboard.Pedalboard`/plugin instance) must happen once, in the `Compile<X>Step` function body itself, not inside the `CompiledEffectStep` closure it returns — that closure runs every block.
3. **`pedalboard.Pedalboard.process()` must be called with `reset=True`** (the default) for every Effect Step, not `reset=False`. `reset=False` is pedalboard's true low-latency streaming mode, but it holds samples back internally and returns a *shorter* block than it was given until enough state accumulates — incompatible with this project's fixed-block-size `outdata[:] = ...` contract. `reset=True` avoids that at the cost of not carrying DSP state across block boundaries (acceptable unless a specific Effect Step's acceptance criteria require it, as ring modulation's phase-continuity test does — see Slice 13 in SLICES.md).
4. **Block size trades off latency against processing headroom.** `pedalboard.PitchShift` has a large, roughly fixed per-call cost that barely scales with block size, so a small block size just means that fixed cost blows the budget more badly. That fixed cost also scales with **sample rate**, not just block size: benchmarked at ~50ms/call at 48kHz vs ~18ms/call at 16kHz (speech content is almost entirely below 8kHz — the Nyquist limit at 16kHz — so there's genuinely less signal to analyze at the lower rate, not just a smaller budget). `SAMPLE_RATE=16000` / `BLOCKSIZE=1024` (64ms budget, ~64ms one-way latency) gives that ~18ms cost a ~2.6x margin (benchmarked p99/max across 150 calls) — a big improvement over the original underflow/overflow fix's `SAMPLE_RATE=48000` / `BLOCKSIZE=8192` (170ms budget/latency), without reintroducing the glitching. Below ~512 samples at 16kHz the margin gets uncomfortably thin (768 samples spiked over budget once in testing) — 1024 is the practical floor found so far without a proper streaming/ring-buffer architecture. If a new Effect Step type turns out to be similarly expensive, benchmark it the same way (call it in a loop, compare per-call time to `BLOCKSIZE / SAMPLE_RATE`, try lower sample rates too) before assuming the existing values have enough headroom — don't guess.

## Testing notes

- `ACTIVE_VOICE_HOLDER` (in `app.py`) is a single shared module-level global that persists across the whole pytest process — it is not reset between tests. Any test that selects a non-default Voice (e.g. via `POST /voices/select`) must restore the previously-active Voice afterward (save `ACTIVE_VOICE_HOLDER.Get()` before, restore it in a `finally`), or it leaks state into unrelated tests that assume Passthrough is still active (see `tests/test_deep_voice.py::test_SelectDeepVoiceSetsItAsActive` for the pattern). This will keep coming up as more Voices ship (Magos in Slice 22, Radio Operator in Slice 25). The same hazard applies to `MASTER_VOLUME_HOLDER` (Slice 13 onward) — see `tests/test_set_volume.py` for that pattern.
