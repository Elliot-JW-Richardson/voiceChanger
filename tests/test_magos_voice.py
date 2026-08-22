"""Tests for the shipped Magos Voice (Slice 22).

Verification (from SLICES.md, Slice 22):
- Given the shipped Magos Voice definition
- When the Voice Bank is loaded
- Then Magos appears with its full pitch-shift, ring-modulation, and
  distortion chain in the declared order, and is selectable and becomes
  active exactly like any other Voice

Magos briefly used a `vocoder` Effect Step instead of `ring_mod` (Slice
36), but real-hardware testing found the vocoder destroyed voice
intelligibility outright (it discards the input's own waveform and
resynthesizes from a detected pitch plus a coarse envelope), and a
follow-up "mix a sawtooth into the voice" experiment (`sawtooth_blend`)
also failed on real hardware. Both were removed and Magos reverted to
this ring_mod-based chain -- the last version confirmed to actually sound
like a voice (see voices/magos.yaml's header comment for the full
history).

Following tests/test_deep_voice.py's precedent, this loads the REAL
`voices/` directory shipped with the project (not a synthetic tmp_path
fixture), to prove the actual shipped `voices/magos.yaml` content is
correct. Following tests/test_select_voice.py's precedent, selection is
verified over HTTP via Flask's test client, checking both the response
body and `ACTIVE_VOICE_HOLDER` directly (imported from `app`) to confirm
the active Voice actually changed.
"""
from pathlib import Path
from typing import Any

from flask.testing import FlaskClient

from app import ACTIVE_VOICE_HOLDER, app
from voice_engine.bank import LoadVoiceBank

VOICES_DIRECTORY_PATH = Path(__file__).parent.parent / "voices"


def test_MagosVoiceShipsWithPitchShiftRingModAndBitcrushChainInOrder() -> None:
    voiceBank = LoadVoiceBank(str(VOICES_DIRECTORY_PATH))

    magosVoice = next(voice for voice in voiceBank.voices if voice.id == "magos")

    assert magosVoice.default is False
    assert len(magosVoice.chain) == 3

    pitchShiftStep, ringModStep, bitcrushStep = magosVoice.chain

    assert pitchShiftStep.type == "pitch_shift"
    assert pitchShiftStep.params["semitones"] < -6

    assert ringModStep.type == "ring_mod"
    assert ringModStep.params["frequency"] > 0

    assert bitcrushStep.type == "bitcrush"
    # Raised from an original <= 8 sanity bound: bit_depth had to go up to
    # 10 to stay intelligible on quiet real microphone input rather than
    # collapsing to a handful of distinct values (see git history and
    # CONTEXT.md's Effect palette entry on pedalboard.Bitcrush's
    # fixed-scale quantization).
    assert 1 <= bitcrushStep.params["bit_depth"] <= 12


def test_SelectMagosVoiceSetsItAsActive() -> None:
    client: FlaskClient = app.test_client()
    previouslyActiveVoice = ACTIVE_VOICE_HOLDER.Get()

    try:
        response = client.post("/voices/select", json={"id": "magos"})
        body: Any = response.get_json()

        assert body["status"] == "ok"
        assert body["activeVoiceId"] == "magos"
        assert ACTIVE_VOICE_HOLDER.Get().id == "magos"
    finally:
        # ACTIVE_VOICE_HOLDER is a shared module-level global (see
        # CLAUDE.md's Testing notes) that outlives this test within the
        # pytest process -- restore it so other test modules that assume
        # the default active Voice aren't affected by test ordering.
        ACTIVE_VOICE_HOLDER.Set(previouslyActiveVoice)
