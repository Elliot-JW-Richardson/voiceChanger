# Slices — pitch-shifted DSP voice changer with switchable voice bank

> Generated from CONTEXT.md and ADR 0001. Run `/execute-slice` to begin.
> Slices are ordered so the product is always runnable — each slice adds one capability on top of passing tests.

---

# Band 1 — Voice Bank and live selection (Passthrough only)
> **Mini-MVP:** Open the page, see the available Voices (just Passthrough for now), and select one — the selection takes effect on the live audio engine, and the old raw pitch slider is gone entirely.

## Slice 1 — Effect Step chain processor  _(Component: Effect Engine)_

**Goal:** Provide the core mechanism that applies an ordered list of Effect Steps to a block of audio, correctly handling the case of no steps at all.

**Verification:**
- Given a Voice's chain contains no Effect Steps
- When a block of audio is processed through it
- Then the output block is identical to the input block

**Completion promise:** `SLICE_1_DONE`
**Depends on:** none
**Status:** done

## Slice 2 — Voice loaded from a single definition  _(Component: Voice Bank)_

**Goal:** Parse one Voice definition into a Voice with its id, name, default flag, and ordered Effect Steps.

**Verification:**
- Given a Voice definition describing an id, a name, and an ordered list of Effect Steps
- When it is loaded
- Then the resulting Voice exposes that same id, name, and ordered Effect Steps

**Completion promise:** `SLICE_2_DONE`
**Depends on:** Slice 1
**Status:** done

## Slice 3 — Voice Bank loads every Voice  _(Component: Voice Bank)_

**Goal:** Discover and load every Voice definition into a single in-memory Voice Bank, identifying which one is marked default.

**Verification:**
- Given several Voice definitions are present, one of them marked as default
- When the Voice Bank is loaded
- Then it contains one Voice per definition and correctly identifies the default Voice

**Completion promise:** `SLICE_3_DONE`
**Depends on:** Slice 2
**Status:** done

## Slice 4 — Passthrough Voice ships as the default  _(Component: Voice Bank)_

**Goal:** Provide the Passthrough Voice (empty chain) as a real, shipped Voice definition marked default.

**Verification:**
- Given the shipped Passthrough Voice definition
- When the Voice Bank is loaded
- Then Passthrough appears with an empty chain and is selected as the default Voice

**Completion promise:** `SLICE_4_DONE`
**Depends on:** Slice 3
**Status:** done

## Slice 5 — Active Voice holder  _(Component: Runtime)_

**Goal:** Track exactly one currently active Voice, safely readable and settable, initialized from the Voice Bank's default.

**Verification:**
- Given a loaded Voice Bank
- When the active Voice holder is initialized from it and then set to a different Voice
- Then reading it right after initialization returns the default Voice, and reading it after the update returns the newly set Voice

**Completion promise:** `SLICE_5_DONE`
**Depends on:** Slice 4
**Status:** done

## Slice 6 — Live audio routed through the active Voice  _(Component: Runtime)_

**Goal:** Replace the direct mic-to-speaker copy with processing through the currently active Voice's chain.

**Verification:**
- Given the active Voice is Passthrough
- When a block of microphone audio is processed
- Then the output block equals the input block, produced via the active-Voice mechanism rather than a direct copy

**Completion promise:** `SLICE_6_DONE`
**Depends on:** Slice 5, Slice 1
**Status:** done

## Slice 7 — List available Voices  _(Component: Voice Selection API)_

**Goal:** Expose the Voice Bank's contents and the current active Voice over HTTP.

**Verification:**
- Given the Voice Bank contains Passthrough
- When the voice list is requested
- Then the response lists Passthrough by id and name and marks it as the active Voice

**Completion promise:** `SLICE_7_DONE`
**Depends on:** Slice 6, Slice 4
**Status:** done

## Slice 8 — Voice list appears on the page  _(Component: Voice Selection UI)_

**Goal:** Render the available Voices as selectable options on the page, replacing the old pitch slider.

**Verification:**
- Given the page is opened
- When it loads
- Then a selectable option for Passthrough is shown, and the old pitch slider is no longer present

**Completion promise:** `SLICE_8_DONE`
**Depends on:** Slice 7
**Status:** done

## Slice 9 — Select a Voice  _(Component: Voice Selection API)_

**Goal:** Let a request set which Voice is currently active; this replaces and retires the old manual pitch-update endpoint entirely.

**Verification:**
- Given the Voice Bank contains Passthrough
- When a request selects Passthrough by id
- Then the active Voice becomes Passthrough and the response confirms it

**Completion promise:** `SLICE_9_DONE`
**Depends on:** Slice 8, Slice 5
**Status:** done

## Slice 10 — Selecting a Voice from the page  _(Component: Voice Selection UI)_

**Goal:** Let clicking a Voice option on the page select it and show it as the active Voice.

**Verification:**
- Given the Voice list is shown on the page
- When a Voice option is clicked
- Then the page shows that Voice as the active one

**Completion promise:** `SLICE_10_DONE`
**Depends on:** Slice 9, Slice 8
**Status:** done

---

# Band 2 — First audible character: Deep Voice
> **Mini-MVP:** Select "Deep" on the page and hear your voice pitched down live — the first audibly transformed character voice, riding entirely on the Band 1 selection mechanism.

## Slice 11 — Pitch shift Effect Step  _(Component: Effect Engine)_

**Goal:** Add pitch shift as a usable Effect Step in a Voice's chain.

**Verification:**
- Given a chain containing a pitch-shift Effect Step set to a number of semitones
- When a block of audio is processed through it
- Then the output audio's pitch is shifted by that amount

**Completion promise:** `SLICE_11_DONE`
**Depends on:** Slice 1
**Status:** done

## Slice 12 — Deep Voice  _(Component: Voice Bank)_

**Goal:** Ship a second Voice, built purely from a pitch-shift Effect Step, so a first audibly distinct character is selectable end-to-end.

**Verification:**
- Given the shipped Deep Voice definition
- When the Voice Bank is loaded
- Then Deep Voice appears alongside Passthrough with its pitch-shift Effect Step, and is selectable and becomes active exactly like any other Voice

**Completion promise:** `SLICE_12_DONE`
**Depends on:** Slice 11
**Status:** done

---

# Band 3 — Master Volume control
> **Mini-MVP:** Drag the volume slider on the page and hear the output get quieter or louder live, no matter which Voice is selected. Added out of plan order after real-hardware testing of Deep Voice reported the output as too quiet (see ADR 0002); prioritized ahead of Bands 4-5 at the user's request.

## Slice 13 — Master Volume holder  _(Component: Runtime)_

**Goal:** Track a single global Master Volume level, safely readable and settable, defaulting to 100% (unchanged output).

**Verification:**
- Given the Master Volume holder is initialized
- When it is read before any change, and then set to a different level and read again
- Then the first read reports 100%, and the second read reports the newly set level

**Completion promise:** `SLICE_13_DONE`
**Depends on:** none
**Status:** done

## Slice 14 — Live audio gain applied via Master Volume  _(Component: Runtime)_

**Goal:** Scale the live audio callback's output by the Master Volume level (originally 0-200%, later raised to 0-400% after real-world testing — see CONTEXT.md), clipping to the valid audio range to prevent distortion when boosting.

**Verification:**
- Given the Master Volume is set to a level that would push a loud block's samples beyond the valid [-1, 1] range
- When that block is processed
- Then the output is scaled by the volume level and clipped so no sample exceeds [-1, 1]

**Completion promise:** `SLICE_14_DONE`
**Depends on:** Slice 13, Slice 6
**Status:** done

## Slice 15 — Get current volume  _(Component: Master Volume API)_

**Goal:** Expose the current Master Volume level over HTTP.

**Verification:**
- Given the Master Volume is at its default level
- When the volume is requested
- Then the response reports 100%

**Completion promise:** `SLICE_15_DONE`
**Depends on:** Slice 13
**Status:** done

## Slice 16 — Volume slider appears on the page  _(Component: Master Volume UI)_

**Goal:** Render a volume slider on the page reflecting the current Master Volume level, alongside (not replacing) Voice selection.

**Verification:**
- Given the page is opened
- When it loads
- Then a volume slider is shown, positioned at the current Master Volume level

**Completion promise:** `SLICE_16_DONE`
**Depends on:** Slice 15
**Status:** done

## Slice 17 — Set volume  _(Component: Master Volume API)_

**Goal:** Let a request set the Master Volume level, clamped to the valid range (originally 0-200%, later raised to 0-400% after real-world testing — see CONTEXT.md).

**Verification:**
- Given a request sets the Master Volume to a specific level within the valid range
- When the volume is read back
- Then it reflects the new level

**Completion promise:** `SLICE_17_DONE`
**Depends on:** Slice 16, Slice 13
**Status:** done

## Slice 18 — Dragging the slider updates volume  _(Component: Master Volume UI)_

**Goal:** Let moving the volume slider on the page set the Master Volume live.

**Verification:**
- Given the volume slider is shown on the page
- When it is moved to a new level
- Then the new level is sent to set the Master Volume

**Completion promise:** `SLICE_18_DONE`
**Depends on:** Slice 17, Slice 16
**Status:** done

---

# Band 4 — The flagship robotic character: Magos Voice
> **Mini-MVP:** Select "Magos" on the page and hear a pitched-down, robotic, distorted voice live — the flagship cosplay character voice.

## Slice 19 — Ring modulation Effect Step  _(Component: Effect Engine)_

**Goal:** Add ring modulation (metallic/robotic buzz) as a usable Effect Step, with its oscillator phase carrying continuously across successive blocks.

**Verification:**
- Given a chain containing a ring-modulation Effect Step
- When two consecutive blocks of audio are processed through it
- Then the oscillator's phase at the start of the second block continues seamlessly from where it left off at the end of the first, with no discontinuity at the boundary

**Completion promise:** `SLICE_19_DONE`
**Depends on:** Slice 1
**Status:** done

## Slice 20 — Distortion/bitcrush Effect Step  _(Component: Effect Engine)_

**Goal:** Add distortion/bitcrush as a usable Effect Step for adding grit to a Voice.

**Verification:**
- Given a chain containing a bitcrush Effect Step set to a reduced bit depth
- When a smooth block of audio is processed through it
- Then the output contains only the limited number of distinct sample values that bit depth allows, confirming quantization occurred

**Completion promise:** `SLICE_20_DONE`
**Depends on:** Slice 1
**Status:** done

## Slice 21 — Effect Steps compose in declared order  _(Component: Effect Engine)_

**Goal:** Confirm a chain of multiple different Effect Steps applies them in the order declared, not some other order.

**Verification:**
- Given a chain declaring a ring-modulation step followed by a bitcrush step
- When a block of audio is processed through it
- Then the result matches applying ring modulation first and bitcrush second, and differs from applying them in the reverse order

**Completion promise:** `SLICE_21_DONE`
**Depends on:** Slice 19, Slice 20
**Status:** done

## Slice 22 — Magos Voice  _(Component: Voice Bank)_

**Goal:** Ship the Warhammer 40K Magos-style Voice — pitch shift, ring modulation, and distortion chained together — as a selectable Voice.

**Verification:**
- Given the shipped Magos Voice definition
- When the Voice Bank is loaded
- Then Magos appears with its full pitch-shift, ring-modulation, and distortion chain in the declared order, and is selectable and becomes active exactly like any other Voice

**Completion promise:** `SLICE_22_DONE`
**Depends on:** Slice 21, Slice 11
**Status:** done

---

# Band 5 — Full palette and a third example Voice
> **Mini-MVP:** The full effect palette (pitch shift, ring modulation, distortion, EQ, reverb) is available, and the Voice Bank ships three distinct example character voices alongside Passthrough — all switchable live from the page.

## Slice 23 — EQ (shelf) Effect Step  _(Component: Effect Engine)_

**Goal:** Add a low/high shelf EQ as a usable Effect Step for shaping a Voice's tone.

**Verification:**
- Given a chain containing an EQ Effect Step boosting a shelf band
- When a block containing a frequency inside that band and one outside it is processed through it
- Then the in-band frequency's amplitude increases relative to the out-of-band frequency's, compared to the unprocessed input

**Completion promise:** `SLICE_23_DONE`
**Depends on:** Slice 1
**Status:** done

## Slice 24 — Reverb Effect Step  _(Component: Effect Engine)_

**Goal:** Add reverb as a usable Effect Step for spatial character.

**Verification:**
- Given a chain containing a reverb Effect Step with a non-zero wet level
- When a short impulse of audio is processed through it
- Then the output contains a decay tail extending beyond the impulse's original position

**Completion promise:** `SLICE_24_DONE`
**Depends on:** Slice 1
**Status:** done

## Slice 25 — Radio Operator Voice  _(Component: Voice Bank)_

**Goal:** Ship a further example Voice combining EQ and reverb with existing effects, rounding out the example Voice Bank.

**Verification:**
- Given the shipped Radio Operator Voice definition
- When the Voice Bank is loaded
- Then Radio Operator appears with its declared chain including the EQ and reverb steps, and is selectable and becomes active exactly like any other Voice

**Completion promise:** `SLICE_25_DONE`
**Depends on:** Slice 23, Slice 24
**Status:** todo

---

# Band 6 — Noise Gate control
> **Mini-MVP:** Drag the noise gate slider on the page and background noise gets filtered out before it ever reaches the Voice's effect chain, no matter which Voice is selected. Added after real-world testing of Magos reported the output as "mumbly" and wanting background-noise filtering (see CONTEXT.md's Noise Gate entry). Mirrors Band 3 (Master Volume)'s structure exactly, applied to the raw input before the Voice chain instead of the output after it.

## Slice 26 — Noise Gate holder  _(Component: Runtime)_

**Goal:** Track a single global Noise Gate sensitivity level, safely readable and settable, defaulting to 0% (gate fully open, no gating).

**Verification:**
- Given the Noise Gate holder is initialized
- When it is read before any change, and then set to a different level and read again
- Then the first read reports 0%, and the second read reports the newly set level

**Completion promise:** `SLICE_26_DONE`
**Depends on:** none
**Status:** todo

## Slice 27 — Live audio gated before the Voice chain  _(Component: Runtime)_

**Goal:** Attenuate the live audio callback's raw microphone input by the Noise Gate level before it reaches the active Voice's chain, filtering background noise while passing voice through largely unaffected.

**Verification:**
- Given the Noise Gate is set to a level that would attenuate a quiet, noise-like block
- When that block is processed
- Then the output is measurably attenuated compared to processing it with the gate fully open, while a louder, voice-like block above the threshold remains largely unaffected

**Completion promise:** `SLICE_27_DONE`
**Depends on:** Slice 26, Slice 6
**Status:** todo

## Slice 28 — Get current noise gate level  _(Component: Noise Gate API)_

**Goal:** Expose the current Noise Gate level over HTTP.

**Verification:**
- Given the Noise Gate is at its default level
- When the level is requested
- Then the response reports 0%

**Completion promise:** `SLICE_28_DONE`
**Depends on:** Slice 26
**Status:** todo

## Slice 29 — Noise gate slider appears on the page  _(Component: Noise Gate UI)_

**Goal:** Render a noise gate slider on the page reflecting the current level, alongside (not replacing) Master Volume and Voice selection.

**Verification:**
- Given the page is opened
- When it loads
- Then a noise gate slider is shown, positioned at the current Noise Gate level

**Completion promise:** `SLICE_29_DONE`
**Depends on:** Slice 28
**Status:** todo

## Slice 30 — Set noise gate level  _(Component: Noise Gate API)_

**Goal:** Let a request set the Noise Gate level, clamped to the valid 0-100% range.

**Verification:**
- Given a request sets the Noise Gate to a specific level within the valid range
- When the level is read back
- Then it reflects the new level

**Completion promise:** `SLICE_30_DONE`
**Depends on:** Slice 29, Slice 26
**Status:** todo

## Slice 31 — Dragging the noise gate slider updates the level  _(Component: Noise Gate UI)_

**Goal:** Let moving the noise gate slider on the page set the Noise Gate level live.

**Verification:**
- Given the noise gate slider is shown on the page
- When it is moved to a new level
- Then the new level is sent to set the Noise Gate

**Completion promise:** `SLICE_31_DONE`
**Depends on:** Slice 30, Slice 29
**Status:** todo

---

# Band 7 — Vocoder: pitch-tracked, formant-preserving Magos
> **Mini-MVP:** Speak into the mic with Magos active and hear a pitch-tracked, harmonically-rich electronic voice that still clearly says your words — built from spectral analysis of a real reference track (see ADR 0004), not guesswork. Directly targets both the character-matching goal and the "mumbly" complaint (naive pitch-shift smears formants; a vocoder explicitly preserves them). Built in four genuine stages, each an audible milestone — no throwaway work, pitch tracking is a real prerequisite of the final result, not a detour. Sequenced ahead of the LLVC spike (still deliberately last) since this directly addresses reported quality issues.

## Slice 32 — Pitch tracker detects a known frequency  _(Component: Vocoder)_

**Goal:** Provide a real-time-safe pitch (fundamental frequency) detector that estimates a block's dominant pitch via autocorrelation.

**Verification:**
- Given a block containing a pure tone of a known frequency
- When the pitch tracker analyzes it
- Then it reports a detected frequency close to the known frequency

**Completion promise:** `SLICE_32_DONE`
**Depends on:** none
**Status:** todo

## Slice 33 — Vocoder Effect Step: pitch-tracked sawtooth carrier  _(Component: Vocoder)_

**Goal:** Add "vocoder" as a usable Effect Step whose output is a sawtooth oscillator carrier tracking the input block's detected pitch, replacing the block's own waveform with that carrier — a stepping-stone milestone toward full formant vocoding, audible in its own right.

**Verification:**
- Given a chain containing a vocoder Effect Step and a two-block input where the detected pitch differs between the blocks
- When the blocks are processed through it
- Then each output block's dominant frequency matches that block's own detected input pitch, and the output's spectrum shows the rich multi-harmonic structure of a sawtooth wave rather than a single sine tone

**Completion promise:** `SLICE_33_DONE`
**Depends on:** Slice 32, Slice 1
**Status:** todo

## Slice 34 — Vocoder applies the modulator's formant envelope to the carrier  _(Component: Vocoder)_

**Goal:** Extend the vocoder Effect Step to shape the pitch-tracked sawtooth carrier with the input voice's own spectral envelope (via a filter bank + envelope followers), turning the raw carrier from Slice 33 into a true formant-vocoded, intelligible signal.

**Verification:**
- Given a chain containing a vocoder Effect Step and two different input signals that share the same pitch but differ in spectral/formant shape
- When each is processed through it
- Then the two outputs differ from each other in spectral shape, proving the carrier is shaped by each input's own envelope rather than output as a flat sawtooth, while both retain the same underlying pitch

**Completion promise:** `SLICE_34_DONE`
**Depends on:** Slice 33
**Status:** todo

## Slice 35 — Vocoder switches to a noise carrier for unvoiced input  _(Component: Vocoder)_

**Goal:** Detect when a block has no clear pitch (unvoiced/consonant-like input, e.g. "s", "f", "sh") and use a noise carrier instead of the pitched sawtooth, avoiding an incorrectly tonal sound on consonants.

**Verification:**
- Given a chain containing a vocoder Effect Step and an input block that is noise-like with no clear pitch
- When it is processed through it
- Then the output is noise-carrier-based rather than a tonal sawtooth at some spuriously detected pitch, while a separate clearly-pitched block in the same test still produces the pitched sawtooth carrier as before

**Completion promise:** `SLICE_35_DONE`
**Depends on:** Slice 33
**Status:** todo

## Slice 36 — Magos Voice uses the vocoder  _(Component: Voice Bank)_

**Goal:** Re-tune the Magos Voice to use the new vocoder Effect Step, closing the loop from the reference-track analysis (ADR 0004) to an actual audible result.

**Verification:**
- Given the updated Magos Voice definition
- When the Voice Bank is loaded
- Then Magos's chain includes the vocoder Effect Step, and is selectable and becomes active exactly like any other Voice

**Completion promise:** `SLICE_36_DONE`
**Depends on:** Slice 35, Slice 34, Slice 22
**Status:** todo

---

# Band 8 — LLVC feasibility spike
> **Mini-MVP:** A recorded, evidence-based answer to "is LLVC viable for this project," backed by real installation and timing data from this desktop machine — not a shipped feature. See ADR 0003 for context. Unlike Bands 1-7, these are investigative spikes, not TDD feature slices: a slice ending "blocked" with clearly recorded findings is a legitimate, expected outcome here, not a failure. Deliberately sequenced last — see the conversation around ADR 0003 for why (no other Band depends on this, and isolating a heavy new dependency stack like PyTorch is cleanest done once the DSP work is stable).

## Slice 37 — LLVC installs in an isolated environment  _(Component: ML Voice Spike)_

**Goal:** Determine whether LLVC's dependencies install successfully in an isolated environment, resolving the Python 3.9-vs-3.11 question (ADR 0003) empirically rather than by assumption.

**Verification:**
- Given a fresh, isolated Python environment separate from this project's main venv
- When LLVC's dependencies are installed per its own repository instructions
- Then the outcome (success, or the exact failure) is recorded for Python 3.9, and for Python 3.11 if 3.9 fails

**Completion promise:** `SLICE_37_DONE`
**Depends on:** none
**Status:** todo

## Slice 38 — LLVC offline inference smoke test  _(Component: ML Voice Spike)_

**Goal:** Run LLVC's offline `infer.py` against a short sample audio clip and measure wall-clock conversion time on this desktop machine.

**Verification:**
- Given LLVC installed (Slice 37) and a short sample audio clip
- When `infer.py` is run against it using a pretrained checkpoint
- Then the conversion completes and the measured time, compared to the clip's duration, produces a real-time factor for this desktop machine

**Completion promise:** `SLICE_38_DONE`
**Depends on:** Slice 37
**Status:** todo

## Slice 39 — LLVC simulated-streaming latency measurement  _(Component: ML Voice Spike)_

**Goal:** Measure per-chunk latency using LLVC's simulated-streaming mode, as the closest available proxy for real-time feasibility before Raspberry Pi hardware exists.

**Verification:**
- Given LLVC installed (Slice 37)
- When its simulated-streaming inference mode (the `-s` flag) is run against a sample input
- Then per-chunk latency is measured and recorded, and compared against this project's established real-time budget (the ~139ms budget from CLAUDE.md's Real-time performance notes) as an optimistic desktop-class upper bound — not a Pi-equivalent result

**Completion promise:** `SLICE_39_DONE`
**Depends on:** Slice 37
**Status:** todo

## Slice 40 — Record findings in ADR 0003  _(Component: ML Voice Spike)_

**Goal:** Synthesize Slices 38-39's findings into ADR 0003 and CONTEXT.md, replacing "unverified" with measured numbers and a concrete recommendation on whether to pursue LLVC further.

**Verification:**
- Given the recorded findings from Slices 38-39
- When ADR 0003 and CONTEXT.md's LLVC scoping note are updated
- Then they state the actual measured installation outcome, real-time factor, and simulated-streaming latency, with an explicit recommendation (proceed to real Pi hardware testing once purchased, or abandon the LLVC direction) instead of the current placeholder language

**Completion promise:** `SLICE_40_DONE`
**Depends on:** Slice 38, Slice 39
**Status:** todo
