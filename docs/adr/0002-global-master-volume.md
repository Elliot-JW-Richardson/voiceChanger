# Master Volume is a global control, not a per-Voice setting

Status: accepted

Real-hardware testing after Deep Voice shipped found the live output too quiet. We added a Master Volume: a single global gain (0-200%, default 100%) applied after whichever Voice's Effect Step chain runs, rather than a `gain`-style Effect Step each Voice would need to declare individually. The reported problem was general ("everything is quiet"), not specific to one Voice's chain, and a global control is reachable no matter which Voice is selected without needing every current and future Voice file to carry its own compensating gain value.

## Considered options

- **Per-Voice gain Effect Step** — more precise (a naturally quiet effect chain could be pre-compensated in its own YAML), but doesn't address a general "the whole app is quiet" problem without duplicating a gain value across every Voice file, and adds a Voice-authoring burden for something that isn't really a Voice-specific characteristic.
- **Global Master Volume (chosen)** — one control, independent of Voice selection, directly matches how the problem was reported and observed.
