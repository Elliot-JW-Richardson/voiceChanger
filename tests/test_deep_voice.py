"""Tests for the shipped Deep Voice (Slice 12).

Verification (from SLICES.md, Slice 12):
- Given the shipped Deep Voice definition
- When the Voice Bank is loaded
- Then Deep Voice appears alongside Passthrough with its pitch-shift
  Effect Step, and is selectable and becomes active exactly like any
  other Voice

Following tests/test_passthrough_voice.py's precedent, this loads the
REAL `voices/` directory shipped with the project (not a synthetic
tmp_path fixture), to prove the actual shipped `voices/deep.yaml`
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


def test_DeepVoiceShipsWithPitchShiftChainAlongsidePassthrough() -> None:
    voiceBank = LoadVoiceBank(str(VOICES_DIRECTORY_PATH))

    deepVoice = next(voice for voice in voiceBank.voices if voice.id == "deep")
    passthroughVoice = next(voice for voice in voiceBank.voices if voice.id == "passthrough")

    assert deepVoice.name == "Deep"
    assert deepVoice.default is False
    assert len(deepVoice.chain) == 1
    assert deepVoice.chain[0].type == "pitch_shift"
    assert deepVoice.chain[0].params["semitones"] < 0
    assert passthroughVoice in voiceBank.voices


def test_SelectDeepVoiceSetsItAsActive() -> None:
    client: FlaskClient = app.test_client()
    previouslyActiveVoice = ACTIVE_VOICE_HOLDER.Get()

    try:
        response = client.post("/voices/select", json={"id": "deep"})
        body: Any = response.get_json()

        assert body["status"] == "ok"
        assert body["activeVoiceId"] == "deep"
        assert ACTIVE_VOICE_HOLDER.Get().id == "deep"
    finally:
        # ACTIVE_VOICE_HOLDER is a shared module-level global (see
        # CLAUDE.md's Architecture notes) that outlives this test within
        # the pytest process -- restore it so other test modules that
        # assume the default active Voice (e.g. test_list_voices.py)
        # aren't affected by test ordering.
        ACTIVE_VOICE_HOLDER.Set(previouslyActiveVoice)
