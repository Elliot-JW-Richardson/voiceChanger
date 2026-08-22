"""Tests for the shipped Radio Operator Voice (Slice 25).

Verification (from SLICES.md, Slice 25):
- Given the shipped Radio Operator Voice definition
- When the Voice Bank is loaded
- Then Radio Operator appears with its declared chain including the EQ
  and reverb steps, and is selectable and becomes active exactly like
  any other Voice

Following tests/test_magos_voice.py's precedent, this loads the REAL
`voices/` directory shipped with the project (not a synthetic tmp_path
fixture), to prove the actual shipped `voices/radio_operator.yaml`
content is correct. Following tests/test_select_voice.py's precedent,
selection is verified over HTTP via Flask's test client, checking both
the response body and `ACTIVE_VOICE_HOLDER` directly (imported from
`app`) to confirm the active Voice actually changed.
"""
from pathlib import Path
from typing import Any

from flask.testing import FlaskClient

from app import ACTIVE_VOICE_HOLDER, app
from voice_engine.bank import LoadVoiceBank

VOICES_DIRECTORY_PATH = Path(__file__).parent.parent / "voices"


def test_RadioOperatorVoiceShipsWithEqAndReverbChainInOrder() -> None:
    voiceBank = LoadVoiceBank(str(VOICES_DIRECTORY_PATH))

    radioOperatorVoice = next(
        voice for voice in voiceBank.voices if voice.id == "radio_operator"
    )

    assert radioOperatorVoice.name == "Radio Operator"
    assert radioOperatorVoice.default is False
    assert len(radioOperatorVoice.chain) == 4

    lowCutStep, highCutStep, bitcrushStep, reverbStep = radioOperatorVoice.chain

    # Low-shelf cut: rolls off bass to give the thin, tinny tonal quality
    # of a comms-radio speaker rather than a full-range mic.
    assert lowCutStep.type == "eq"
    assert lowCutStep.params["band"] == "low"
    assert lowCutStep.params["gain_db"] < 0
    assert lowCutStep.params["cutoff_frequency_hz"] > 0

    # High-shelf cut: rolls off treble too, so combined with the
    # low-shelf cut above, the pair band-limits the voice the way a
    # narrow-bandwidth radio transmission does.
    assert highCutStep.type == "eq"
    assert highCutStep.params["band"] == "high"
    assert highCutStep.params["gain_db"] < 0
    assert highCutStep.params["cutoff_frequency_hz"] > lowCutStep.params["cutoff_frequency_hz"]

    # Bitcrush: adds the crackly, static-like grit of a noisy radio
    # transmission on top of the band-limited tone.
    assert bitcrushStep.type == "bitcrush"
    assert 1 <= bitcrushStep.params["bit_depth"] <= 12

    # Reverb: a small amount of tight, boxy space -- evoking a small
    # speaker cabinet/handset, not a hall -- so wet level and room size
    # both stay modest rather than lush.
    assert reverbStep.type == "reverb"
    assert 0 < reverbStep.params["wet_level"] < 0.5
    assert 0 < reverbStep.params["room_size"] < 0.5


def test_SelectRadioOperatorVoiceSetsItAsActive() -> None:
    client: FlaskClient = app.test_client()
    previouslyActiveVoice = ACTIVE_VOICE_HOLDER.Get()

    try:
        response = client.post("/voices/select", json={"id": "radio_operator"})
        body: Any = response.get_json()

        assert body["status"] == "ok"
        assert body["activeVoiceId"] == "radio_operator"
        assert ACTIVE_VOICE_HOLDER.Get().id == "radio_operator"
    finally:
        # ACTIVE_VOICE_HOLDER is a shared module-level global (see
        # CLAUDE.md's Testing notes) that outlives this test within the
        # pytest process -- restore it so other test modules that assume
        # the default active Voice aren't affected by test ordering.
        ACTIVE_VOICE_HOLDER.Set(previouslyActiveVoice)
