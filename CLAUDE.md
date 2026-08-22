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
- Sample rate and block size are set as module-level constants in both `app.py` and `main.py`, currently duplicated between them rather than shared, and **differ between the two on purpose**: `app.py` uses 22050 Hz / 3072 (see the "Real-time performance" note below); `main.py` (no DSP, just a raw pass-through) stays at 48000 Hz / 1024 — it doesn't need the lower sample rate's processing headroom, and 48kHz is the more useful setting for a general "does my audio hardware work" sanity check. Both are mono (1 channel).
- `ApplyMasterVolume` (in `voice_engine/engine.py`) uses `pedalboard.Gain` + `pedalboard.Limiter` rather than plain linear gain with `np.clip` — a limiter allows pushing much closer to full scale on quiet input without harsh clipping, which plain hard-clip gain can't do safely (see the function's own docstring for the full reasoning and benchmark numbers). It special-cases `level == 100` to bypass Gain/Limiter and return the block completely unchanged — without that, the Limiter can still soften a near-full-scale sample even at nominal 0dB gain, which would break the Passthrough Voice's "truly unmodified signal" guarantee at default settings.
- Input/output devices are left at system defaults (`sd.Stream` called without a `device=` argument); per-device selection is not implemented.

### Real-time performance (read before adding a new Effect Step type)

`AudioCallback` runs once per audio block on sounddevice's real-time thread and must complete within `BLOCKSIZE / SAMPLE_RATE` seconds or the stream audibly glitches (`Status: output underflow` / `input overflow` printed to the console, heard as static). Two real bugs already hit this, both fixed in the same pass (not a planned slice — see git history around the Slice 12 follow-up commits):

1. **Don't recompile the chain every block.** `CompileChain` can be expensive per Effect Step (see #2). `AudioCallback` must go through `COMPILED_CHAIN_CACHE` (`CompiledChainCache` in `voice_engine/engine.py`), which only recompiles when the active Voice's id actually changes, not on every block.
2. **Don't do expensive per-step setup inside the compiled closure.** A `Compile<X>Step` function's expensive part (e.g. constructing a `pedalboard.Pedalboard`/plugin instance) must happen once, in the `Compile<X>Step` function body itself, not inside the `CompiledEffectStep` closure it returns — that closure runs every block.
3. **`pedalboard.Pedalboard.process()` must be called with `reset=True`** (the default) for every Effect Step, not `reset=False`. `reset=False` is pedalboard's true low-latency streaming mode, but it holds samples back internally and returns a *shorter* block than it was given until enough state accumulates — incompatible with this project's fixed-block-size `outdata[:] = ...` contract. `reset=True` avoids that at the cost of not carrying DSP state across block boundaries (acceptable unless a specific Effect Step's acceptance criteria require it, as ring modulation's phase-continuity test does — see Slice 13 in SLICES.md).
4. **Block size trades off latency against processing headroom.** `pedalboard.PitchShift` has a large, roughly fixed per-call cost that barely scales with block size, so a small block size just means that fixed cost blows the budget more badly. That fixed cost also scales with **sample rate**, not just block size: less signal to analyze at a lower rate, not just a smaller budget. `SAMPLE_RATE=22050` / `BLOCKSIZE=3072` (139ms budget, ~139ms one-way latency) is the current setting — chosen for a real clarity improvement (11025Hz Nyquist vs 16kHz's 8000Hz, after 16kHz was reported as making speech sound "mumbly") while keeping a solid real-time margin (benchmarked 0/300 calls over budget across independent runs against the full Magos chain, worst observed max ~1.25-1.66x under budget). Lower sample rates give more processing headroom at the cost of audio bandwidth/clarity; this project's history has moved between 48000/8192 → 16000/1024 → 22050/3072 as different problems (underflow, latency, mumbliness) got fixed in turn — expect this to keep being retuned.
5. **ALWAYS benchmark against the heaviest Voice actually shipped, never a single Effect Step in isolation.** The 16000/1024 setting this replaced was validated only against pitch shift alone (Slice 11, before ring modulation or bitcrush existed) and looked comfortably safe (~2.6x margin) — but once Magos (pitch shift + ring mod + bitcrush chained, Slice 22) existed, the *same* 16000/1024 setting showed real occasional budget overruns (~1.7% of calls in one 300-call test) that the single-effect benchmark had completely missed. Check `voices/*.yaml` for the current heaviest chain (currently `magos.yaml`) and benchmark the full chain, including `ApplyMasterVolume` at a non-100% level, not just the raw Effect Steps. This machine's benchmarks also show real run-to-run jitter — a config that shows 0 overruns in one run can show several in another — so look for a comfortable margin across multiple independent runs, not a single clean-looking one.
6. **Slice 36 update — Magos now chains vocoder → pitch_shift → bitcrush (ring_mod removed, see ADR 0004 and `voices/magos.yaml`'s own comments), making it heavier than the old ring_mod-based chain** (the vocoder Effect Step adds autocorrelation pitch detection plus an 8-filter-pass-per-band × 4-band filter bank applied twice per block — see `voice_engine/engine.py`'s `CompileVocoderStep` docstring). Benchmarked at the current `SAMPLE_RATE=22050`/`BLOCKSIZE=3072` (139ms budget) against this exact chain plus `ApplyMasterVolume` at 150%, using a moderate/quiet realistic voice-like synthetic input (not silence, not full-scale): across six independent runs, five showed 0/300 calls over budget and one showed 1/300 (a single ~202ms outlier, consistent with this machine's already-documented run-to-run jitter, point 5 above — not a systematic regression), p99 ranging ~56-94ms, typical worst-case max ~106-138ms (~1.01-1.31x under budget). Comfortably safe on the whole — no `SAMPLE_RATE`/`BLOCKSIZE` retune was needed despite the vocoder's added cost.
7. **CHAIN ORDER MATTERS when an Effect Step's own internal analysis (e.g. `vocoder`'s pitch tracking + formant filter bank) assumes a particular input register.** Slice 36 originally shipped Magos as `pitch_shift → vocoder → bitcrush`, on the theory that pitch-shifting first would land the vocoder's tracked pitch closer to ADR 0004's low target register. This broke the vocoder on real hardware: a voice already shifted down ~44% (-10 semitones) lands around 50-90Hz, below `CompileVocoderStep`'s filter bank's lowest band edge (`FILTER_BANK_LOW_HZ=150`, tuned in Slice 34 against natural-register test tones) — the carrier's true fundamental gets filtered away, leaving erratic stray harmonics ("squeaks"). Fixed by reordering to `vocoder → pitch_shift → bitcrush`: the vocoder tracks/shapes the voice at the natural register its filter bank was actually tuned for, and `pitch_shift` transposes the whole finished, already-vocoded signal down afterward as a unit (see `voices/magos.yaml`'s "ORDERING FIX" comment for the full diagnosis, verified via a synthetic swept-pitch diagnostic). General lesson: when chaining a pitch-altering step with a step that does its own internal pitch/frequency analysis, put the analyzing step first, or explicitly verify (don't assume) that its tuned frequency assumptions still hold against whatever the upstream steps hand it.

## Testing notes

- `ACTIVE_VOICE_HOLDER` (in `app.py`) is a single shared module-level global that persists across the whole pytest process — it is not reset between tests. Any test that selects a non-default Voice (e.g. via `POST /voices/select`) must restore the previously-active Voice afterward (save `ACTIVE_VOICE_HOLDER.Get()` before, restore it in a `finally`), or it leaks state into unrelated tests that assume Passthrough is still active (see `tests/test_deep_voice.py::test_SelectDeepVoiceSetsItAsActive` for the pattern). This will keep coming up as more Voices ship (Magos in Slice 22, Radio Operator in Slice 25). The same hazard applies to `MASTER_VOLUME_HOLDER` (Slice 13 onward) — see `tests/test_set_volume.py` for that pattern.
