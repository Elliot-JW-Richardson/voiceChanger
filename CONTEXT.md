# Context: Voice Changer

## Domain terms

### Voice
A named, switchable audio transformation applied to the live mic signal to change its perceived character. Two kinds, distinguished by implementation:

- **DSP Voice** — a real-time effect chain (pitch shift, modulation, distortion, EQ, reverb, etc.) applied per audio block. No training data, no GPU, runs entirely in the live callback. This is the target for the current overhaul.
- **ML Voice** — a voice-conversion model conditioned/trained on reference audio to approximate a specific source voice. Deferred to a later phase; out of scope for this overhaul. Needed for voices where a DSP chain can't credibly evoke the target (specific character impressions), as opposed to general robotic/character effects (e.g. the Warhammer 40K Magos voice) which are DSP-only.

Decision: this overhaul targets DSP Voices only, to avoid a GPU/ML dependency up front. ML Voices are a recognized future extension, not a current requirement.

**Candidate engine (scoping only, not adopted):** [LLVC](https://github.com/KoeAI/LLVC) (MIT license) — CPU-only real-time voice conversion, sub-20ms inference latency claimed at 16kHz on a desktop CPU (arXiv:2311.00873). Attractive specifically because it needs no GPU, which was the original reason ML Voice was deferred. Not yet validated for this project — see ADR 0003 for the open prerequisites (Raspberry Pi performance unverified, Python version mismatch, heavy PyTorch dependency, and a real per-target-voice training-data requirement that reopens the IP-sourcing question DSP Voices were chosen partly to sidestep).

### Voice Bank
The data-driven collection of available Voices. Each Voice is defined declaratively (not as hard-coded Python) as an ordered list of effect steps plus their parameters, loaded at runtime rather than compiled into the switching logic. This keeps adding/tuning voices independent of code changes and leaves room for a later entry to reference an ML engine instead of a DSP chain without restructuring how voices are selected.

Stored as one YAML file per Voice in a `voices/` directory (e.g. `voices/magos.yaml`), loaded by scanning the directory at startup. YAML chosen over JSON specifically so voice files can carry `#` comments documenting *why* a parameter is tuned the way it is — expected to be hand-edited by ear frequently. Requires `PyYAML` as a dependency.

**Diagnostic Voices:** to audition where a multi-step chain's problem originates, a `debug-`-prefixed Voice (name prefixed `"DEBUG: "`) whose chain is a prefix of the real Voice's chain can be dropped into `voices/` temporarily and selected live — same mechanism as any other Voice, no code changes needed (first used to isolate a real-hardware Magos vocoder intelligibility issue). Delete once diagnosis is complete; not meant to be long-lived, since they drift out of sync with the Voice they were copied from.

### Passthrough Voice
The trivial Voice: an empty Effect Step chain (mic straight to speaker, today's existing behavior). Not a special hardcoded engine fallback — it's an ordinary entry in the Voice Bank (`voices/passthrough.yaml`), so the engine never special-cases "nothing selected." Marked as the default Voice loaded on startup before any selection is made.

### Effect Step
One entry in a DSP Voice's chain: an effect type plus its parameters (e.g. `{"type": "pitch_shift", "semitones": -6}`). A DSP Voice is an ordered list of Effect Steps applied in sequence to each audio block.

### Effect palette (v1)
The set of Effect Step types the engine supports: **pitch shift**, **ring modulation** (metallic/robotic buzz — multiplies the signal by a sine oscillator), **distortion/bitcrush** (grit), **EQ** (low/high shelf), and **reverb**. All five are real-time-safe via `pedalboard` (ring mod excepted, which is a trivial custom oscillator multiply).

**Bitcrush gotcha (learned the hard way on Magos — see git history):** `pedalboard.Bitcrush` quantizes in fixed steps across the full `[-1, 1]` range, not relative to the actual signal's amplitude. A `bit_depth` that sounds like tasteful grit against a full-scale test tone can collapse a quiet real microphone signal (this hardware's mic is already known to be quiet — see the Master Volume entry) to only a handful of distinct values, heard as buzzy squeaks rather than a voice. When tuning or adding a bitcrush-using Voice, verify against a realistic quiet input amplitude, not just a loud test tone — see `tests/test_bitcrush_step.py::test_BitcrushStepStaysReasonablyIntelligibleOnQuietRealisticInput` for the pattern.

**Formant shift** (alters vocal-tract resonance independent of pitch) is a recognized future effect type, deferred out of v1: it has no drop-in real-time implementation (classically LPC or phase-vocoder based) and doesn't fit the small-buffer live-callback model the rest of the palette is built around. Superseded in practice by the **vocoder** Effect Step (see below), which explicitly extracts and preserves formant/spectral-envelope information as part of its design — the standalone "formant shift" idea is no longer the active plan.

### Vocoder Effect Step (v2, scoped — see ADR 0004; shipped but NOT currently used by any Voice — see below)
A distinct Effect Step type from the rest of the palette: it combines a **carrier** (a sawtooth oscillator, pitch-tracked to follow the input voice's own detected pitch in real time) with the input voice's own **modulator envelope** (its spectral/formant shape, extracted via a filter bank + envelope followers and imposed onto the carrier) — the classic talkbox/vocoder technique. Built in stages (see SLICES.md's Vocoder Band): pitch tracking, a pitch-tracked sawtooth carrier alone, then envelope-shaped vocoding via a 4-band filter bank, then voiced/unvoiced handling so unpitched consonants use a noise carrier instead of an incorrectly tonal sawtooth.

**Real-hardware finding: this does NOT work as intended.** Once wired into Magos (Slice 36) and tested with a real voice (not synthetic test tones, which is all the unit tests and prototyping ever validated it against), the vocoder destroyed intelligibility outright — even in isolation (no pitch shift, no bitcrush), it produced buzz with no detectable speech. The leading suspect is the filter bank's 4 bands being far too coarse to reconstruct real vocal formants (professional vocoders commonly use 8-20+); pitch-tracking reliability on real (non-tonal) speech is also unvalidated. A follow-up attempt to MIX a pitch-tracked sawtooth into the voice instead of replacing it (`sawtooth_blend`, an additive rather than resynthesis approach) was also tried and also failed on real hardware (extremely loud output, still no audible speech) — both `sawtooth_blend`'s code and its WIP Voice were removed rather than left half-working. `vocoder` itself remains in `voice_engine/engine.py`, unused by any shipped Voice.

**Superseded by a re-tuned `ring_mod`-based Magos, not another vocoder attempt (see ADR 0005).** Properly re-analysing the reference audio — with a real pitch tracker across two independent reference sources, not just re-reading ADR 0004's summary — found the target fundamental is mostly FLAT/held at a low resting pitch (~45-58Hz) with ordinary speech-prosody rises at stressed syllables, not a continuously moving melody as ADR 0004 originally described. That's architecturally a much better fit for `ring_mod`'s fixed-frequency carrier than for a real-time pitch-*tracking* vocoder — the vocoder rebuild solved a problem (melody-tracking) the target didn't actually have. Magos's `ring_mod` frequency is now tuned to match its own post-pitch-shift fundamental (see `voices/magos.yaml`'s header comment), which reproduces the reference's measured "2nd harmonic louder than the fundamental" signature. Candidate chains were validated by testing against real recordings of the user's own voice and comparing measured output (fundamental, spectral centroid, rolloff, harmonic ratios) against the reference's own measured profile — not just "sounds okay on a synthetic tone," the gap that let the vocoder's failure go undetected until real hardware.

### Master Volume
A single global gain control applied to the live audio output after a Voice's Effect Step chain, independent of which Voice is active — not a Voice, not an Effect Step, and not per-Voice. Chosen deliberately (see ADR 0002) after real-hardware testing reported the output as too quiet: a general "the whole thing is too quiet" problem is best solved by one control reachable regardless of which Voice is selected, rather than requiring every current and future Voice to individually compensate for it. Represented as a percentage, 0-400% (100% = unity gain, unchanged output; raised from an initial 0-200% ceiling after real-world use found even 200% wasn't loud enough) — implemented as `pedalboard.Gain` followed by `pedalboard.Limiter` (raised from an initial plain-linear-gain-plus-hard-clip implementation, which had to stay conservative to avoid clipping the loudest peaks and so left quiet real microphone input still too quiet; a limiter allows pushing much closer to full scale safely). 100% is special-cased to bypass Gain/Limiter entirely and return the signal completely unmodified, preserving the Passthrough Voice's guarantee at default settings.

### Noise Gate
A single global control, applied to the raw microphone input BEFORE a Voice's Effect Step chain runs — the mirror image of Master Volume, which applies AFTER. Attenuates/mutes audio below a threshold, filtering background noise while letting voice through. Global and pre-chain for the same reasons Master Volume is global and post-chain (see ADR 0002): a general "cut background noise" need, reachable regardless of which Voice is selected, not a per-Voice characteristic. Implemented via `pedalboard.NoiseGate`. Represented as a sensitivity percentage, 0-100% (0% = gate fully open, no gating — matches this project's convention of a "no effect" default, e.g. Master Volume's 100%).

**Real-hardware limitation (level-based, not adaptive):** real-hardware testing after Slice 27-31 shipped found the gate does cut faint, steady background buzzing as intended, but percussive/broadband transients (e.g. keyboard clicks) that briefly exceed the amplitude threshold still get through, since `pedalboard.NoiseGate` only judges loudness, not whether a sound is noise-shaped or voice-shaped. An adaptive/spectral gate that distinguishes sustained voice energy from transient noise is a recognized future improvement — not yet scoped as a slice.

## Deployment scope

Development and testing happen on the desktop (Windows) for now. The eventual target is a small, cheap, standalone SBC (Raspberry Pi Zero 2 W is the current front-runner, not yet purchased/committed) mounted in a cosplay headpiece, running headless with the audio stream auto-starting on boot and voice selection done via phone browser over the Pi's own WiFi AP. Hardware selection and porting are deferred — not part of this overhaul.

A separate servo-skull computer-vision project was raised and explicitly ruled **out of scope** here: it will not share a board with this voice module. No CV-related requirements should influence this design.

## Relationships

- A **Voice Bank** contains many **Voices**; exactly one Voice is active in the engine at a time.
- A **DSP Voice** is composed of an ordered list of **Effect Steps**; the list may be empty (the **Passthrough Voice**).
- The manual pitch slider (`/update_pitch`, `current_pitch_semitones`) is retired entirely once Voices ship. Voice selection is the only control surface — no raw pitch value floating independent of a selected Voice.
- Switching the active Voice is expected to produce a brief audible glitch (effect state resets); seamless crossfade between Voices is explicitly not a goal.
- **Master Volume** applies after whichever Voice is active; it is not part of any Voice's chain and is unaffected by switching Voices.

## Example dialogue

> **Dev:** "So when I add a new character, I just drop a YAML file in `voices/`?"
> **Domain expert:** "Right — as long as it's a **DSP Voice**. If it needs an **ML Voice** to sound convincing, that's a different, deferred mechanism."
> **Dev:** "And if I want it robotic like the Magos voice?"
> **Domain expert:** "Chain a pitch shift with ring modulation and some distortion — those are just more **Effect Steps** in the same list."

## Flagged ambiguities

- "Arduino or Raspberry Pi" was used loosely for the eventual portable target — resolved: only a Raspberry Pi (Linux-capable SBC) is viable for this Python/`pedalboard`-based engine; a classic Arduino cannot run this stack. Specific model not yet committed.
