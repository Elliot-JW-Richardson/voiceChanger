# LLVC identified as the candidate ML Voice engine (not yet adopted)

Status: proposed

This records scoping, not a decision: [LLVC](https://github.com/KoeAI/LLVC) (Konstantine Sadov et al., Koe AI, MIT license, arXiv:2311.00873) is the leading candidate for the deferred **ML Voice** category (see CONTEXT.md's Voice entry). It's attractive because it runs real-time voice conversion on CPU alone — sub-20ms inference latency and ~2.8x faster than real-time, as published — which directly answers the reason ML Voice was deferred in the first place (avoiding a GPU dependency). Those published figures were measured on an Intel i9-10850K desktop CPU, not any Raspberry Pi, and the project's own README flags that eval.py needs Python 3.9 while the main environment instructions target Python 3.11 — this project's venv is pinned to 3.9 throughout.

Nothing has been built or committed to yet. No SLICES.md entries exist for this. If pursued, the next concrete step is a cheap smoke test on the dev desktop — install LLVC in an isolated environment (not the main venv, given the Python version question), run its offline `infer.py` on a sample, and measure timing — before spending any further effort, and certainly before any Raspberry Pi purchase decision (still open per CONTEXT.md's Deployment scope).

## Open prerequisites (all unresolved)

1. **Raspberry Pi CPU performance is unverified.** The published benchmark hardware is vastly more powerful per-core than the Pi Zero 2 W currently fronted as the deployment target. "Fast on an i9" says nothing about "fast on a Pi."
2. **Python version mismatch.** LLVC's own instructions target Python 3.11 (with a 3.9 carve-out only for `eval.py`); this project's venv is pinned to Python 3.9 throughout. Unclear yet whether LLVC's core inference path actually works on 3.9 or whether ML Voice work would need a separate environment/Python version, complicating the "one `venv`, one `requirements.txt`" setup this project currently has.
3. **Heavy dependency footprint.** LLVC requires PyTorch and torchaudio. Both are large, and ARM/Raspberry-Pi CPU wheels for PyTorch are known to be less straightforward than x86 — install feasibility and runtime memory footprint (relevant given the Pi Zero 2 W's 512MB RAM) are unverified.
4. **"Any-to-one" needs a real training dataset, not just reference clips.** LLVC's training data format is paired `(original, converted-to-target)` audio across many source speakers, mapped to one target voice — this is a dataset-assembly and model-training effort per new ML Voice, not a "drop in a few seconds of reference audio" operation. Training would happen off-Pi (desktop/cloud); only the resulting checkpoint would ship to the device for inference.
5. **Sourcing training pairs reopens the IP question.** Point 4 means adding an ML Voice "as" a specific character requires actual `(source, converted-to-that-character)` training audio — a materially different and murkier proposition than the DSP effect chains chosen for Magos-style voices specifically to sidestep this (see the Voice entry in CONTEXT.md and the original design session).
6. **Integration is custom streaming work, not a drop-in call.** Unlike `pedalboard`'s `Pedalboard.process(block, sampleRate)`, LLVC's out-of-box tooling is an offline conversion script (`infer.py`), with only a `-s` "simulated streaming" flag for latency testing — wiring it into this project's live per-block `AudioCallback` would be genuine integration engineering, not a one-line swap.

## Considered options

- **Do nothing yet (chosen for now)** — capture the scoping, keep DSP Voices as the only active track, revisit once the open prerequisites above are actually investigated.
- **Commit to LLVC now and start building** — rejected: too many unresolved feasibility risks (Pi performance chief among them) to justify slice-planning effort yet.
