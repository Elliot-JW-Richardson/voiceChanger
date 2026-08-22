# Voice Changer

A real-time microphone voice changer. A Flask server routes live microphone input through a switchable **Voice** — a named, data-driven DSP effect chain (pitch shift, ring modulation, distortion, EQ, reverb) — and a small browser page lets you pick which Voice is active. Originally started as a plain mic pass-through experiment; being rebuilt slice by slice into the voice changer described in [CONTEXT.md](CONTEXT.md).

Currently only the **Passthrough** Voice (no effects) is shipped — see [SLICES.md](SLICES.md) for what's built so far and what's next.

## Prerequisites

- Python 3.14
- Windows (the existing venv and setup are Windows-oriented; a working microphone/speaker setup is required to actually hear anything)

## Setup

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```
python app.py
```

Then open `http://127.0.0.1:5000/` in a browser, click **Start**, and pick a Voice from the list. **Stop** ends the audio stream.

For a bare microphone/speaker sanity check without Flask or the Voice system — useful for confirming your audio hardware works at all — run:

```
python main.py
```

(Ctrl+C to stop. This always does a raw pass-through; it does not route through the Voice Bank.)

## Running tests

```
pytest
```

## Project docs

- [CLAUDE.md](CLAUDE.md) — codebase guidance: architecture, code style conventions, running instructions for contributors/AI assistants
- [CONTEXT.md](CONTEXT.md) — domain vocabulary and design decisions (what a "Voice" is, the effect palette, deployment scope)
- [docs/adr/](docs/adr/) — architecture decision records
- [SLICES.md](SLICES.md) — the incremental build plan and current progress
