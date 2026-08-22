"""Tests for the shipped Magos Voice (Slice 22, chain composition revised
in Slice 36).

Verification (from SLICES.md, Slice 36 -- supersedes Slice 22's original
chain-composition verification):
- Given the updated Magos Voice definition
- When the Voice Bank is loaded
- Then Magos's chain includes the vocoder Effect Step, and is selectable
  and becomes active exactly like any other Voice

Following tests/test_master_volume_gain.py's precedent for documenting a
revised test: `test_MagosVoiceShipsWithPitchShiftRingModAndBitcrushChainInOrder`
(Slice 22) is revised here to
`test_MagosVoiceShipsWithPitchShiftVocoderAndBitcrushChainInOrder`
because Magos's chain composition intentionally changed -- per ADR 0004
("Build a real vocoder rather than tune ring modulation further"), the
vocoder Effect Step REPLACES ring modulation rather than supplementing
it: a fixed-frequency carrier (ring_mod) can't reproduce the
melody-tracking harmonic series the reference track's analysis found,
and the vocoder's pitch-tracked sawtooth/noise carrier already produces
a buzzy/robotic timbre on its own, making ring_mod redundant once
vocoder exists. `pitch_shift` and `bitcrush` are unaffected by this
revision and keep their original assertions.

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


def test_MagosVoiceShipsWithPitchShiftVocoderAndBitcrushChainInOrder() -> None:
    voiceBank = LoadVoiceBank(str(VOICES_DIRECTORY_PATH))

    magosVoice = next(voice for voice in voiceBank.voices if voice.id == "magos")

    assert magosVoice.default is False
    assert len(magosVoice.chain) == 3

    pitchShiftStep, vocoderStep, bitcrushStep = magosVoice.chain

    assert pitchShiftStep.type == "pitch_shift"
    assert pitchShiftStep.params["semitones"] < -6

    # No params required (see voice_engine/voice.py's ParseEffectStep and
    # voice_engine/engine.py's CompileVocoderStep) -- just confirms the
    # step is present, in the middle of the chain, between pitch_shift and
    # bitcrush.
    assert vocoderStep.type == "vocoder"

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
