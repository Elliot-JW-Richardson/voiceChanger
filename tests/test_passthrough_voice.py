"""Tests for the shipped Passthrough Voice (Slice 4).

Verification (from SLICES.md, Slice 4):
- Given the shipped Passthrough Voice definition
- When the Voice Bank is loaded
- Then Passthrough appears with an empty chain and is selected as the
  default Voice

Unlike test_bank.py's Slice 3 test, this loads the REAL `voices/`
directory shipped with the project (not a synthetic tmp_path fixture),
to prove the actual shipped `voices/passthrough.yaml` content is correct.
"""
from pathlib import Path

from voice_engine.bank import LoadVoiceBank

VOICES_DIRECTORY_PATH = Path(__file__).parent.parent / "voices"


def test_PassthroughVoiceShipsWithEmptyChainAndIsDefault() -> None:
    voiceBank = LoadVoiceBank(str(VOICES_DIRECTORY_PATH))

    passthroughVoice = next(voice for voice in voiceBank.voices if voice.id == "passthrough")

    assert passthroughVoice.name == "Passthrough"
    assert passthroughVoice.chain == []
    assert passthroughVoice.default is True
    assert voiceBank.defaultVoice == passthroughVoice
