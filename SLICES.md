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

**Goal:** Scale the live audio callback's output by the Master Volume level (0-200%), clipping to the valid audio range to prevent distortion when boosting.

**Verification:**
- Given the Master Volume is set to a level that would push a loud block's samples beyond the valid [-1, 1] range
- When that block is processed
- Then the output is scaled by the volume level and clipped so no sample exceeds [-1, 1]

**Completion promise:** `SLICE_14_DONE`
**Depends on:** Slice 13, Slice 6
**Status:** todo

## Slice 15 — Get current volume  _(Component: Master Volume API)_

**Goal:** Expose the current Master Volume level over HTTP.

**Verification:**
- Given the Master Volume is at its default level
- When the volume is requested
- Then the response reports 100%

**Completion promise:** `SLICE_15_DONE`
**Depends on:** Slice 13
**Status:** todo

## Slice 16 — Volume slider appears on the page  _(Component: Master Volume UI)_

**Goal:** Render a volume slider on the page reflecting the current Master Volume level, alongside (not replacing) Voice selection.

**Verification:**
- Given the page is opened
- When it loads
- Then a volume slider is shown, positioned at the current Master Volume level

**Completion promise:** `SLICE_16_DONE`
**Depends on:** Slice 15
**Status:** todo

## Slice 17 — Set volume  _(Component: Master Volume API)_

**Goal:** Let a request set the Master Volume level, clamped to the valid 0-200% range.

**Verification:**
- Given a request sets the Master Volume to a specific level within the valid range
- When the volume is read back
- Then it reflects the new level

**Completion promise:** `SLICE_17_DONE`
**Depends on:** Slice 16, Slice 13
**Status:** todo

## Slice 18 — Dragging the slider updates volume  _(Component: Master Volume UI)_

**Goal:** Let moving the volume slider on the page set the Master Volume live.

**Verification:**
- Given the volume slider is shown on the page
- When it is moved to a new level
- Then the new level is sent to set the Master Volume

**Completion promise:** `SLICE_18_DONE`
**Depends on:** Slice 17, Slice 16
**Status:** todo

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
**Status:** todo

## Slice 20 — Distortion/bitcrush Effect Step  _(Component: Effect Engine)_

**Goal:** Add distortion/bitcrush as a usable Effect Step for adding grit to a Voice.

**Verification:**
- Given a chain containing a bitcrush Effect Step set to a reduced bit depth
- When a smooth block of audio is processed through it
- Then the output contains only the limited number of distinct sample values that bit depth allows, confirming quantization occurred

**Completion promise:** `SLICE_20_DONE`
**Depends on:** Slice 1
**Status:** todo

## Slice 21 — Effect Steps compose in declared order  _(Component: Effect Engine)_

**Goal:** Confirm a chain of multiple different Effect Steps applies them in the order declared, not some other order.

**Verification:**
- Given a chain declaring a ring-modulation step followed by a bitcrush step
- When a block of audio is processed through it
- Then the result matches applying ring modulation first and bitcrush second, and differs from applying them in the reverse order

**Completion promise:** `SLICE_21_DONE`
**Depends on:** Slice 19, Slice 20
**Status:** todo

## Slice 22 — Magos Voice  _(Component: Voice Bank)_

**Goal:** Ship the Warhammer 40K Magos-style Voice — pitch shift, ring modulation, and distortion chained together — as a selectable Voice.

**Verification:**
- Given the shipped Magos Voice definition
- When the Voice Bank is loaded
- Then Magos appears with its full pitch-shift, ring-modulation, and distortion chain in the declared order, and is selectable and becomes active exactly like any other Voice

**Completion promise:** `SLICE_22_DONE`
**Depends on:** Slice 21, Slice 11
**Status:** todo

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
**Status:** todo

## Slice 24 — Reverb Effect Step  _(Component: Effect Engine)_

**Goal:** Add reverb as a usable Effect Step for spatial character.

**Verification:**
- Given a chain containing a reverb Effect Step with a non-zero wet level
- When a short impulse of audio is processed through it
- Then the output contains a decay tail extending beyond the impulse's original position

**Completion promise:** `SLICE_24_DONE`
**Depends on:** Slice 1
**Status:** todo

## Slice 25 — Radio Operator Voice  _(Component: Voice Bank)_

**Goal:** Ship a further example Voice combining EQ and reverb with existing effects, rounding out the example Voice Bank.

**Verification:**
- Given the shipped Radio Operator Voice definition
- When the Voice Bank is loaded
- Then Radio Operator appears with its declared chain including the EQ and reverb steps, and is selectable and becomes active exactly like any other Voice

**Completion promise:** `SLICE_25_DONE`
**Depends on:** Slice 23, Slice 24
**Status:** todo
