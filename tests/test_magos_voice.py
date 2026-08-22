"""Tests for the shipped Magos Voice (Slice 22).

Verification (from SLICES.md, Slice 22):
- Given the shipped Magos Voice definition
- When the Voice Bank is loaded
- Then Magos appears with its full pitch-shift, ring-modulation, and
  distortion chain in the declared order, and is selectable and becomes
  active exactly like any other Voice

Magos briefly used a `vocoder` Effect Step instead of `ring_mod` (Slice
36), but real-hardware testing found the vocoder destroyed voice
intelligibility outright, and a follow-up "mix a sawtooth into the
voice" experiment (`sawtooth_blend`) also failed on real hardware. Both
were removed and Magos reverted to this ring_mod-based chain, then
RE-TUNED (pitch_shift depth, ring_mod frequency, a new EQ step, and
finally a modest gain+limiter for loudness) after properly analysing
reference audio and testing candidate chains against real recordings of
the user's own voice -- see voices/magos.yaml's header comment for the
full methodology and reasoning, including why a LARGE gain/distortion
boost was tried and rejected (real, measured artifacts) in favor of a
smaller clean boost plus the user's own Master Volume slider for the
rest.

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


def test_MagosVoiceShipsWithFullRetunedChainInOrder() -> None:
    voiceBank = LoadVoiceBank(str(VOICES_DIRECTORY_PATH))

    magosVoice = next(voice for voice in voiceBank.voices if voice.id == "magos")

    assert magosVoice.default is False
    assert len(magosVoice.chain) == 6

    pitchShiftStep, ringModStep, bitcrushStep, eqStep, gainStep, limiterStep = magosVoice.chain

    assert pitchShiftStep.type == "pitch_shift"
    # Deepened from an original -10 (see git history and
    # voices/magos.yaml's header comment) to land the user's own natural
    # speaking pitch inside the reference's measured ~45-58Hz fundamental
    # range.
    assert pitchShiftStep.params["semitones"] < -10

    assert ringModStep.type == "ring_mod"
    # Retuned to sit close to the expected post-shift fundamental itself
    # (rather than an arbitrary "robotic buzz" frequency) -- see
    # voices/magos.yaml's header comment for why this specific
    # relationship matters (it's what reproduces the reference's
    # 2nd-harmonic-dominant signature).
    assert 40 <= ringModStep.params["frequency"] <= 70

    assert bitcrushStep.type == "bitcrush"
    # Raised from an original <= 8 sanity bound: bit_depth had to go up to
    # 10 to stay intelligible on quiet real microphone input rather than
    # collapsing to a handful of distinct values (see git history and
    # CONTEXT.md's Effect palette entry on pedalboard.Bitcrush's
    # fixed-scale quantization).
    assert 1 <= bitcrushStep.params["bit_depth"] <= 12

    assert eqStep.type == "eq"
    assert eqStep.params["band"] == "high"
    assert eqStep.params["gain_db"] > 0

    assert gainStep.type == "gain"
    # A DELIBERATELY modest boost -- a much larger value was tried and
    # produced real, measured rhythmic-ticking/burst-noise artifacts
    # (see voices/magos.yaml's header comment); this sanity bound exists
    # to catch someone reintroducing that mistake, not to pin an exact
    # value.
    assert 0 < gainStep.params["gain_db"] <= 15

    assert limiterStep.type == "limiter"
    # REQUIRED alongside `gain` -- not caught by ApplyMasterVolume's own
    # limiter, which is bypassed at the default 100% Master Volume level
    # (see CompileGainStep's docstring in voice_engine/engine.py).
    assert limiterStep.params["threshold_db"] < 0


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
