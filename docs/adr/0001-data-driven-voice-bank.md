# Data-driven Voice Bank instead of hard-coded voice functions

Status: accepted

We need an open-ended, growable library of Voices (character/effect presets), not a fixed handful. Each Voice is defined declaratively — an ordered list of effect steps plus parameters — and loaded at runtime from a Voice Bank, rather than implemented as individual hard-coded Python functions. This lets voices be added or tuned without touching switching/engine code, and leaves a clean seam for a later voice entry to reference an ML engine instead of a DSP chain without restructuring how voices are selected.

## Considered options

- **Hard-coded Python functions per voice** — simplest to write for a handful of voices, but ties adding/tuning a voice to a code change, and gives no natural place to later distinguish a DSP voice from an ML voice.
- **Data-driven Voice Bank (chosen)** — adds a small schema/registry layer up front, but scales to an open-ended, hand-tunable voice library and generalizes to future ML voices.
