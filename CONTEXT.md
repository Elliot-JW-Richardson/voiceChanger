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

### Passthrough Voice
The trivial Voice: an empty Effect Step chain (mic straight to speaker, today's existing behavior). Not a special hardcoded engine fallback — it's an ordinary entry in the Voice Bank (`voices/passthrough.yaml`), so the engine never special-cases "nothing selected." Marked as the default Voice loaded on startup before any selection is made.

### Effect Step
One entry in a DSP Voice's chain: an effect type plus its parameters (e.g. `{"type": "pitch_shift", "semitones": -6}`). A DSP Voice is an ordered list of Effect Steps applied in sequence to each audio block.

### Effect palette (v1)
The set of Effect Step types the engine supports: **pitch shift**, **ring modulation** (metallic/robotic buzz — multiplies the signal by a sine oscillator), **distortion/bitcrush** (grit), **EQ** (low/high shelf), and **reverb**. All five are real-time-safe via `pedalboard` (ring mod excepted, which is a trivial custom oscillator multiply).

**Bitcrush gotcha (learned the hard way on Magos — see git history):** `pedalboard.Bitcrush` quantizes in fixed steps across the full `[-1, 1]` range, not relative to the actual signal's amplitude. A `bit_depth` that sounds like tasteful grit against a full-scale test tone can collapse a quiet real microphone signal (this hardware's mic is already known to be quiet — see the Master Volume entry) to only a handful of distinct values, heard as buzzy squeaks rather than a voice. When tuning or adding a bitcrush-using Voice, verify against a realistic quiet input amplitude, not just a loud test tone — see `tests/test_bitcrush_step.py::test_BitcrushStepStaysReasonablyIntelligibleOnQuietRealisticInput` for the pattern.

**Formant shift** (alters vocal-tract resonance independent of pitch) is a recognized future effect type, deferred out of v1: it has no drop-in real-time implementation (classically LPC or phase-vocoder based) and doesn't fit the small-buffer live-callback model the rest of the palette is built around. Revisit once the Voice Bank architecture is proven end-to-end.

### Master Volume
A single global gain control applied to the live audio output after a Voice's Effect Step chain, independent of which Voice is active — not a Voice, not an Effect Step, and not per-Voice. Chosen deliberately (see ADR 0002) after real-hardware testing reported the output as too quiet: a general "the whole thing is too quiet" problem is best solved by one control reachable regardless of which Voice is selected, rather than requiring every current and future Voice to individually compensate for it. Represented as a percentage, 0-400% (100% = unity gain, unchanged output; raised from an initial 0-200% ceiling after real-world use found even 200% wasn't loud enough) — implemented as `pedalboard.Gain` followed by `pedalboard.Limiter` (raised from an initial plain-linear-gain-plus-hard-clip implementation, which had to stay conservative to avoid clipping the loudest peaks and so left quiet real microphone input still too quiet; a limiter allows pushing much closer to full scale safely). 100% is special-cased to bypass Gain/Limiter entirely and return the signal completely unmodified, preserving the Passthrough Voice's guarantee at default settings.

### Noise Gate
A single global control, applied to the raw microphone input BEFORE a Voice's Effect Step chain runs — the mirror image of Master Volume, which applies AFTER. Attenuates/mutes audio below a threshold, filtering background noise while letting voice through. Global and pre-chain for the same reasons Master Volume is global and post-chain (see ADR 0002): a general "cut background noise" need, reachable regardless of which Voice is selected, not a per-Voice characteristic. Implemented via `pedalboard.NoiseGate`. Represented as a sensitivity percentage, 0-100% (0% = gate fully open, no gating — matches this project's convention of a "no effect" default, e.g. Master Volume's 100%).

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
