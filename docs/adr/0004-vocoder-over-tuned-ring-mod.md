# Build a real vocoder rather than tune ring modulation further

Status: accepted

Magos was reported as "mumbly," and the user supplied a reference track for the target character. Spectral analysis of that track's vocals (isolated using its auto-generated captions to find vocal-only segments) found: a fundamental that moves with the melody (42-58Hz, tracking a descending phrase) rather than sitting at a fixed frequency, a dense near-complete harmonic series through at least the 9th harmonic, and real broadband high-frequency content beyond that series (spectral centroid at 4.1kHz despite 99% of energy sitting under 3.1kHz) consistent with genuine distortion/grit, not just a clean pitched-down voice.

A fixed-frequency carrier (tuning `ring_mod`'s existing sine oscillator, or swapping it for a sawtooth) can't reproduce a harmonic series that tracks pitch — it would always produce sidebands offset from the *voice's* harmonics by a constant carrier frequency, not the clean, melody-tracking series actually observed. Reproducing that requires the carrier's own pitch to track the input, which in turn opens the door to doing this properly: a genuine vocoder (pitch-tracked carrier + the input's own extracted spectral envelope imposed onto it), rather than a partial approximation.

This also directly addresses "mumbly" as a side effect, not just the character-matching goal: naive pitch-shift (the current `pitch_shift` Effect Step) smears formants because it doesn't extract or preserve them; a vocoder explicitly extracts the voice's spectral envelope and imposes it onto the carrier, which is what makes vocoded speech intelligible rather than a formless buzz.

## Considered options

- **Tune `ring_mod`'s carrier (sine or sawtooth, fixed or pitch-tracked-but-no-envelope) further** — cheaper, but provably can't reproduce the reference's melody-tracking harmonic series (fixed carrier) or its speech intelligibility (no formant/envelope preservation either way).
- **Full vocoder (chosen)** — pitch tracking is a genuine prerequisite either way, so building only as far as "option 2" (pitched sawtooth carrier, no envelope shaping) would be a real but incomplete milestone, not a cheaper end state — the remaining work (filter-bank envelope extraction and recombination) is what actually delivers intelligibility and the reference's character. Built in stages so each stage is a genuine, audible, testable milestone rather than one large opaque change (see SLICES.md's Vocoder Band) — real-time performance for the filter bank + envelope followers + pitch tracker is not yet benchmarked and needs verifying against the full worst-case chain during implementation, per the lesson already learned once on this project (see CLAUDE.md's Real-time performance notes).
